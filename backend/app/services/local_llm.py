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
        self.devices = parse_cuda_devices(output)
        if not self.devices:
            logger.error(
                "llama-server tidak melihat GPU CUDA (output: %s) — LLM akan jalan di CPU",
                " ".join(output.split())[:300],
            )
        return self.devices

    def _log_tail_text(self, lines: int = 400) -> str:
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as handle:
                return "\n".join(handle.read().splitlines()[-lines:])
        except Exception:
            return ""

    def start(self) -> bool:
        """Jalankan llama-server dan tunggu sampai siap. False bila gagal."""
        if not self.available:
            return False
        if self.process is not None and self.process.poll() is None and self._healthy():
            return True
        if self._healthy():  # server sudah jalan (mis. dari proses lain)
            return True

        devices = self._detect_devices()
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

        # Coba GPU lebih dulu (pilih device eksplisit), lalu fallback tanpa
        # `--device` bila backend CUDA gagal dimuat — jangan sampai task mati.
        attempts: list[list[str]] = []
        if devices:
            attempts.append(base_cmd + ["--device", "CUDA0"])
        attempts.append(list(base_cmd))

        for cmd in attempts:
            if self._spawn_and_wait(cmd):
                return True
            self.stop()
        return False

    def _spawn_and_wait(self, cmd: list[str]) -> bool:
        """Jalankan satu perintah server dan tunggu /health 200."""
        logger.info("Menjalankan LLM lokal: %s", " ".join(cmd))
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
        """Info runtime terbaru (device + kecepatan decode) setelah inferensi."""
        speed = parse_last_speed(self._log_tail_text(60))
        if speed:
            self.last_speed = speed
        device = self.devices[0][:90] if self.devices else "tidak terdeteksi"
        note = ""
        try:
            value = float(speed.split()[0]) if speed else 0.0
            if value and value < 8.0:
                note = " | PERINGATAN: lambat, kemungkinan CPU fallback"
        except Exception:
            note = ""
        return f"device={device} | speed={speed or 'belum ada'}{note}"[:300]

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
    ) -> Optional[str]:
        """Satu panggilan chat completion. None bila server tidak siap/gagal."""
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
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                timeout=settings.LOCAL_LLM_CHAT_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            self.last_speed = parse_last_speed(self._log_tail_text(60))
            return str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            logger.warning("LLM lokal gagal menjawab: %s", str(exc)[:300])
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
