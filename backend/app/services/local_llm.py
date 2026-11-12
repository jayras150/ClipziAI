"""
LLM lokal di worker GPU — llama.cpp server + Qwen3-4B-Instruct-2507 (GGUF).

Kenapa llama.cpp, bukan transformers/vLLM:
  * tidak butuh torch (image worker sudah punya CTranslate2 CUDA),
  * VRAM kecil: Q4_K_XL ±2,55 GB + KV cache 8k → aman bila dijalankan bergantian
    dengan Whisper large-v3 (Whisper di-unload dulu),
  * server OpenAI-compatible (`/v1/chat/completions`) sehingga kode metadata/
    planner yang ada bisa dipakai tanpa mengubah protokol.

Semua kegagalan di sini **tidak boleh** menggagalkan task: pemanggil harus
menangani `None` dan jatuh ke jalur heuristik.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def parse_json_any(raw: str) -> Any:
    """Ambil nilai JSON pertama (objek ATAU array) dari balasan model.

    Qwen kadang membalas `[{...}]` (array) walau diminta objek, jadi parser harus
    menerima keduanya. `None` bila tidak ada JSON valid.
    """
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    candidates: list[tuple[int, str]] = []
    array_start, array_end = text.find("["), text.rfind("]")
    object_start, object_end = text.find("{"), text.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidates.append((object_start, text[object_start : object_end + 1]))
    if array_start != -1 and array_end > array_start:
        candidates.append((array_start, text[array_start : array_end + 1]))

    # Coba yang posisinya paling awal lebih dulu: JSON objek yang berisi array
    # (mis. {"clips": []}) tidak boleh terbaca sebagai array kosong.
    for _, candidate in sorted(candidates, key=lambda item: item[0]):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Ambil objek JSON pertama dari balasan model (termasuk blok ```json)."""
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_cuda_devices(text: str) -> list[str]:
    """Ambil daftar device CUDA dari keluaran `llama-server --list-devices`.

    Contoh keluaran:
        Available devices:
          CUDA0: NVIDIA GeForce RTX 3060 (12288 MiB, 11388 MiB free)
    """
    devices: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("CUDA"):
            devices.append(stripped[:120])
    return devices


def parse_last_speed(text: str) -> str:
    """Ambil kecepatan decode terakhir dari log llama-server (mis. `tg = 31.4 t/s`)."""
    matches = re.findall(r"tg\s*=\s*([\d.]+)\s*t/s", text or "")
    if not matches:
        return ""
    return f"{matches[-1]} t/s"


OFFLOAD_RE = re.compile(
    r"offloaded\s+(\d+)\s*/\s*(\d+)\s+layers\s+to\s+(GPU|CUDA\d*)", re.IGNORECASE
)
CUDA_INIT_RE = re.compile(
    r"ggml_cuda_init:?\s*found\s+(\d+)\s+CUDA\s+devices?", re.IGNORECASE
)
# Bukti bahwa backend CUDA gagal dimuat, sehingga llama.cpp memakai CPU.
CPU_FALLBACK_MARKERS = (
    "no usable gpu found",
    "compiled without gpu support",
    "failed to load backend",
    "ggml_backend_load",
)


def parse_offload(text):
    """Ambil (layer_ter-offload, total_layer, device) dari log llama-server.

    Contoh: `load_tensors: offloaded 33/33 layers to GPU` atau `... to CUDA0`.
    (0, 0, string kosong) bila baris tidak ada.
    """
    matches = OFFLOAD_RE.findall(text or "")
    if not matches:
        return 0, 0, ""
    offloaded, total, device = matches[-1]
    return int(offloaded), int(total), device


def parse_cuda_device_count(text):
    """Jumlah device CUDA yang diinisialisasi (ggml_cuda_init: found N CUDA devices)."""
    matches = CUDA_INIT_RE.findall(text or "")
    if not matches:
        return 0
    try:
        return int(matches[-1])
    except (TypeError, ValueError):
        return 0


def cuda_fallback_reason(text):
    """Alasan bila log menunjukkan backend CUDA tidak terpakai (CPU fallback)."""
    lowered = (text or "").lower()
    for marker in CPU_FALLBACK_MARKERS:
        if marker in lowered:
            for line in (text or "").splitlines():
                if marker in line.lower():
                    return " ".join(line.split())[:200]
            return marker
    return ""


class LocalLLM:
    """Kelola satu proses `llama-server` untuk satu task."""

    _instance: Optional["LocalLLM"] = None

    def __init__(self) -> None:
        self.port = int(settings.LOCAL_LLM_PORT)
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self.model_name = settings.LOCAL_LLM_MODEL_NAME
        self.model_path = settings.LOCAL_LLM_MODEL_PATH
        self.process: Optional[subprocess.Popen] = None
        self._log_path = "/tmp/llama-server.log"
        self.last_error: str = ""
        self.info: str = ""
        self.devices: list[str] = []
        self.last_speed: str = ""
        self.detect_output: str = ""
        self.probe: Dict[str, Any] = {}
        # Offset log saat server dijalankan: hanya segmen baru yang dinilai,
        # supaya baris CUDA dari proses lama tidak membuat false positive.
        self.log_mark: int = 0

    @classmethod
    def instance(cls) -> "LocalLLM":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def available(self) -> bool:
        if not settings.LOCAL_LLM_ENABLED:
            return False
        if shutil.which(settings.LOCAL_LLM_SERVER_BIN) is None:
            logger.warning(
                "llama-server tidak ditemukan di PATH (%s) — LLM lokal nonaktif",
                settings.LOCAL_LLM_SERVER_BIN,
            )
            return False
        return os.path.exists(self.model_path)

    def _healthy(self) -> bool:
        try:
            response = httpx.get(f"http://127.0.0.1:{self.port}/health", timeout=3.0)
            return response.status_code == 200
        except Exception:
            return False


    def _server_env(self) -> dict:
        """Environment untuk llama-server: utamakan CUDA milik image llama.cpp."""
        env = dict(os.environ)
        extra = ["/opt/llama", "/opt/llama/cuda"]
        current = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(extra + ([current] if current else []))
        # Backend ggml dimuat dari direktori ini (bukan hanya dari PATH).
        env.setdefault("GGML_BACKEND_PATH", "/opt/llama")
        return env

    def _run_quick(self, args: list[str], timeout: int = 25) -> str:
        """Jalankan perintah singkat (mis. --list-devices) dan ambil outputnya."""
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout, env=self._server_env()
            )
            return (proc.stdout or "") + (proc.stderr or "")
        except Exception as exc:
            logger.warning("Perintah %s gagal: %s", args[0], exc)
            return ""

    def _detect_devices(self) -> list[str]:
        """Deteksi GPU lewat `--list-devices` (tanpa memuat model)."""
        output = self._run_quick([settings.LOCAL_LLM_SERVER_BIN, "--list-devices"])
        self.detect_output = output
        self.devices = parse_cuda_devices(output)
        if not self.devices:
            logger.error(
                "llama-server tidak melihat GPU CUDA ; output lengkap: %s — LLM akan jalan di CPU",
                " ".join(output.split())[:1500],
            )
        return self.devices

    def _log_tail_text(self, lines: int = 400) -> str:
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as handle:
                return "\n".join(handle.read().splitlines()[-lines:])
        except Exception:
            return ""

    def _nvidia_smi(self) -> Dict[str, Any]:
        """Baca nama GPU + total/terpakai VRAM (MB) lewat nvidia-smi."""
        result: Dict[str, Any] = {}
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            lines = (proc.stdout or "").strip().splitlines()
            if not lines:
                return result
            parts = [part.strip() for part in lines[0].split(",")]
            result["name"] = parts[0] if parts else ""
            result["total_mb"] = int(float(parts[1])) if len(parts) > 1 and parts[1] else 0
            result["used_mb"] = int(float(parts[2])) if len(parts) > 2 and parts[2] else 0
            result["driver"] = parts[3] if len(parts) > 3 else ""
        except Exception as exc:
            logger.warning("nvidia-smi tidak tersedia: %s", exc)
        return result

    def _fresh_log(self) -> str:
        """Segmen log sejak server terakhir dijalankan."""
        return self._log_text()[self.log_mark:]

    def _log_text(self) -> str:
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()[-300_000:]
        except Exception:
            return ""

    def _vram_used_mb(self) -> int:
        return int(self._nvidia_smi().get("used_mb") or 0)

    def gpu_probe(self, vram_before_mb: int = 0, wait_seconds: float = 30.0) -> Dict[str, Any]:
        """Bukti berlapis bahwa inference benar-benar memakai GPU.

        Urutan bukti: nvidia-smi -> device CUDA pada llama-server -> semua layer
        ter-offload -> ggml_cuda_init -> tidak ada warning CPU -> VRAM naik.
        """
        probe: Dict[str, Any] = {
            "gpu_name": "",
            "vram_total_mb": 0,
            "vram_before_mb": int(vram_before_mb or 0),
            "vram_after_mb": 0,
            "vram_delta_mb": 0,
            "devices": list(self.devices),
            "cuda_devices": 0,
            "offloaded": 0,
            "layers": 0,
            "device": "",
            "speed": "",
            "ok": False,
            "reason": "",
        }
        smi = self._nvidia_smi()
        probe["gpu_name"] = str(smi.get("name") or "")
        probe["vram_total_mb"] = int(smi.get("total_mb") or 0)

        deadline = time.monotonic() + max(0.0, float(wait_seconds))
        while True:
            text = self._fresh_log()
            offloaded, total, _ = parse_offload(text)
            if offloaded and total:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(2.0)

        text = self._fresh_log()
        offloaded, total, device = parse_offload(text)
        probe["offloaded"] = offloaded
        probe["layers"] = total
        probe["device"] = device
        probe["cuda_devices"] = parse_cuda_device_count(text)
        after = self._vram_used_mb()
        probe["vram_after_mb"] = after
        if probe["vram_before_mb"]:
            probe["vram_delta_mb"] = after - probe["vram_before_mb"]
        probe["speed"] = parse_last_speed(text)

        reason = cuda_fallback_reason(text)
        if not probe["devices"]:
            reason = reason or "tidak ada device CUDA pada llama-server"
        elif total and offloaded < total:
            reason = "hanya %d/%d layer ter-offload ke GPU" % (offloaded, total)
        elif not total:
            reason = reason or "log tidak menunjukkan layer ter-offload ke GPU"
        if (
            not reason
            and probe["vram_before_mb"]
            and probe["vram_delta_mb"] < int(settings.LOCAL_LLM_MIN_VRAM_DELTA_MB)
        ):
            reason = "VRAM tidak naik signifikan setelah model dimuat (%d MB)" % (
                probe["vram_delta_mb"]
            )
        probe["ok"] = not reason
        probe["reason"] = reason
        self.probe = probe
        return probe

    def start(self) -> bool:
        """Jalankan llama-server dan tunggu sampai siap. False bila gagal."""
        if not self.available:
            return False
        if self.process is not None and self.process.poll() is None and self._healthy():
            return True
        if self._healthy():  # server sudah jalan (mis. dari proses lain)
            return True

        devices = self._detect_devices()
        vram_before = self._vram_used_mb()
        base_cmd = [
            settings.LOCAL_LLM_SERVER_BIN,
            "-m", self.model_path,
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-ngl", str(settings.LOCAL_LLM_GPU_LAYERS),
            "-c", str(settings.LOCAL_LLM_CTX),
            "--parallel", str(settings.LOCAL_LLM_PARALLEL),
            "--no-webui",
            "--jinja",
        ]

        # Coba GPU lebih dulu (device eksplisit). Percobaan kedua tetap dijalankan
        # walau `--list-devices` kosong: tanpa itu log backend CUDA (dlopen) tidak
        # pernah terekam. Probe tetap menentukan lulus/tidak, jadi tidak ada
        # fallback CPU diam-diam.
        attempts: list[list[str]] = []
        if devices:
            attempts.append(base_cmd + ["--device", "CUDA0"])
        attempts.append(list(base_cmd))

        for cmd in attempts:
            if not self._spawn_and_wait(cmd):
                self.stop()
                continue
            probe = self.gpu_probe(vram_before_mb=vram_before)
            self.info = self._gpu_info()
            if settings.LOCAL_LLM_REQUIRE_GPU and not probe.get("ok"):
                self.last_error = (
                    "GPU tidak dipakai: %s | log: %s"
                    % (probe.get("reason"), self._tail_log(8))
                )[:900]
                logger.error("LLM lokal dimatikan: %s", self.last_error)
                self.stop()
                continue
            return True
        return False

    def _spawn_and_wait(self, cmd: list[str]) -> bool:
        """Jalankan satu perintah server dan tunggu /health 200."""
        logger.info("Menjalankan LLM lokal: %s", " ".join(cmd))
        self.log_mark = len(self._log_text())
        try:
            log_file = open(self._log_path, "ab", buffering=0)
            self.process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=self._server_env(),
            )
        except Exception as exc:
            logger.error("Gagal menjalankan llama-server: %s", exc)
            return False

        deadline = time.monotonic() + settings.LOCAL_LLM_START_TIMEOUT
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                logger.error(
                    "llama-server berhenti saat start (exit %s). Log: %s",
                    getattr(self.process, "returncode", "?"),
                    self._tail_log(),
                )
                return False
            if self._healthy():
                self.info = self._gpu_info()
                logger.info(
                    "LLM lokal siap: %s (ctx=%s, ngl=%s, port=%s) | %s",
                    self.model_name,
                    settings.LOCAL_LLM_CTX,
                    settings.LOCAL_LLM_GPU_LAYERS,
                    self.port,
                    self.info,
                )
                return True
            time.sleep(2.0)

        logger.error(
            "llama-server tidak siap dalam %ss. Log: %s",
            settings.LOCAL_LLM_START_TIMEOUT,
            self._tail_log(),
        )
        return False

    def stop(self) -> None:
        """Matikan server supaya VRAM bebas untuk render ffmpeg."""
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=15)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        logger.info("LLM lokal dihentikan; VRAM dibebaskan untuk render")

    def _gpu_info(self, lines: int = 400) -> str:
        """Ringkas status GPU/CUDA + kecepatan decode terakhir (untuk diagnosa)."""
        text = self._log_tail_text(lines)
        cuda_line = ""
        for line in text.splitlines():
            low = line.lower()
            if "ggml_cuda_init" in low or "cuda0" in low or "using device" in low:
                cuda_line = " ".join(line.split())[:140]
                break
        parts: list[str] = []
        parts.append(
            f"GPU: {self.devices[0][:90]}" if self.devices else "GPU: tidak terdeteksi"
        )
        if cuda_line:
            parts.append(f"log: {cuda_line}")
        speed = parse_last_speed(text)
        if speed:
            parts.append(f"speed: {speed}")
        return " | ".join(parts)[:400]

    def runtime_info(self) -> str:
        """Info runtime terbaru: device, layer ter-offload, VRAM, dan kecepatan."""
        probe = self.probe or {}
        speed = parse_last_speed(self._fresh_log())
        if speed:
            self.last_speed = speed
        else:
            speed = self.last_speed
        device = str(probe.get("device") or "") or (
            self.devices[0][:60] if self.devices else "tidak terdeteksi"
        )
        layers = "%s/%s" % (probe.get("offloaded", 0), probe.get("layers", 0))
        parts = [
            "device=%s" % device,
            "layers=%s" % layers,
            "cuda_devices=%s" % probe.get("cuda_devices", 0),
            "vram=%s->%sMB" % (probe.get("vram_before_mb", 0), probe.get("vram_after_mb", 0)),
            "speed=%s" % (speed or "belum ada"),
        ]
        note = ""
        try:
            value = float(speed.split()[0]) if speed else 0.0
            if value and value < 8.0:
                note = " | PERINGATAN: lambat, kemungkinan CPU fallback"
        except Exception:
            note = ""
        if probe.get("reason"):
            note += " | %s" % probe["reason"]
        return (" | ".join(parts) + note)[:400]

    def _tail_log(self, lines: int = 12) -> str:
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as handle:
                return " | ".join(handle.read().splitlines()[-lines:])
        except Exception:
            return "(log tidak tersedia)"


    # ---------------- inference ----------------
    def chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 900,
        temperature: float = 0.2,
        deadline: Optional[float] = None,
    ) -> Optional[str]:
        """Satu panggilan chat completion. None bila server tidak siap/gagal.

        `deadline` (time.monotonic) membatasi TOTAL waktu termasuk retry, supaya
        LLM lambat tidak pernah menggantung task.
        """
        if not self.start():
            return None
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        attempt = 0
        while attempt < 2:  # retry maksimum 1, tetap di dalam deadline yang sama
            attempt += 1
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 5:
                logger.warning(
                    "Anggaran waktu LLM habis (sisa %.1fs) sebelum panggilan",
                    remaining,
                )
                return None
            read_timeout = float(settings.LOCAL_LLM_REPLY_TIMEOUT)
            if remaining is not None:
                read_timeout = min(read_timeout, max(5.0, remaining))
            timeout = httpx.Timeout(
                connect=10.0, read=read_timeout, write=30.0, pool=10.0
            )
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                data = response.json()
                self.last_speed = parse_last_speed(self._log_tail_text(60))
                return str(data["choices"][0]["message"]["content"])
            except Exception as exc:
                logger.warning(
                    "LLM lokal gagal menjawab (percobaan %d/2): %s",
                    attempt,
                    str(exc)[:300],
                )
                if remaining is not None and remaining <= 20:
                    break
        return None

    def chat_json_any(
        self,
        system: str,
        user: str,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> Any:
        """Chat yang menghasilkan JSON objek/array (None bila tidak valid)."""
        from app.services.local_llm import parse_json_any

        raw = self.chat(system, user, max_tokens=max_tokens, temperature=temperature)
        if raw is None:
            self.last_error = f"chat gagal: {self._tail_log(4)[:300]}"
            return None
        payload = parse_json_any(raw)
        if payload is None:
            self.last_error = f"JSON tidak valid: {raw[:300]}"
            logger.warning("Balasan LLM bukan JSON valid: %s", (raw or "")[:200])
        return payload

    def chat_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 900,
        temperature: float = 0.2,
    ) -> Optional[Dict[str, Any]]:
        """Chat yang wajib menghasilkan objek JSON (None bila tidak valid)."""
        raw = self.chat(system, user, max_tokens=max_tokens, temperature=temperature)
        if raw is None:
            return None
        payload = parse_json_object(raw)
        if payload is None:
            logger.warning("Balasan LLM bukan JSON valid: %s", (raw or "")[:200])
        return payload


def get_local_llm() -> LocalLLM:
    return LocalLLM.instance()
