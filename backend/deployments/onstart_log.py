#!/usr/bin/env python3
"""Kirim log tahap ONSTART ke backend SEBELUM pipeline/download dimulai.

Kenapa file ini ada
-------------------
`worker_log_shipper.py` baru aktif ketika pipeline dijalankan, sehingga semua
kejadian penting sebelumnya (env hilang, GPU tidak terdeteksi, model Whisper
belum ada, bgutil gagal, image salah) tidak pernah sampai ke dashboard admin.
Admin hanya melihat task "queued" tanpa penjelasan.

Script ini dipanggil dari `pipeline_onstart.sh` sedini mungkin — setelah image
container jalan, tetapi SEBELUM download/pipeline apa pun — dan mengirim baris
log ke endpoint yang sama dengan shipper (`POST /api/internal/worker/logs`).

Pemakaian:
    python onstart_log.py "pesan" [--stage boot] [--level INFO]
    python onstart_log.py --probe          # kirim ringkasan env/GPU/model

Semua kegagalan diabaikan (exit 0): logging tidak boleh menggagalkan task.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request

TOKEN = (os.environ.get("CLIPZI_WORKER_TOKEN") or "").strip()
TASK_ID = (os.environ.get("CLIPZI_TASK_ID") or "").strip()
CALLBACK = (os.environ.get("CLIPZI_CALLBACK_URL") or "").strip()
API = (
    os.environ.get("CLIPZI_API_BASE")
    or (CALLBACK.split("/api/internal/")[0] if CALLBACK else "")
).rstrip("/")

_INSTANCE_RAW = (
    os.environ.get("VAST_CONTAINERLABEL") or os.environ.get("CONTAINER_ID") or ""
).strip()
try:
    INSTANCE_ID = int("".join(ch for ch in _INSTANCE_RAW if ch.isdigit()) or 0) or None
except Exception:  # noqa: BLE001
    INSTANCE_ID = None

# Urutan seq harus konsisten dengan shipper agar tidak bentrok di DB
# (unique index task_id+seq). Shipper mulai dari 1, jadi pre-log memakai
# rentang negatif? Tidak: DB memakai seq > 0. Kita pakai seq kecil 1..N dan
# shipper melanjutkan dari offset yang dikirim lewat env CLIPZI_LOG_SEQ_OFFSET.
SEQ_OFFSET = int(os.environ.get("CLIPZI_LOG_SEQ_OFFSET") or 0)


def _post(lines: list[dict]) -> bool:
    if not API or not TOKEN or not lines:
        return False
    body = json.dumps(
        {"task_id": TASK_ID or None, "instance_id": INSTANCE_ID, "lines": lines}
    ).encode()
    request = urllib.request.Request(
        API + "/api/internal/worker/logs",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Clipzi-Token": TOKEN,
            # Cloudflare memblokir User-Agent default urllib (error 1010/403).
            "User-Agent": "ClipziAI-Worker/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status < 400
    except Exception:  # noqa: BLE001 - logging tidak boleh menggagalkan task
        return False


def _run(command: str, timeout: int = 10) -> str:
    try:
        out = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return ((out.stdout or "") + (out.stderr or "")).strip()
    except Exception:  # noqa: BLE001
        return ""


def _probe_lines() -> list[dict]:
    """Ringkasan kondisi instance saat boot (tanpa menjalankan pipeline)."""
    lines: list[dict] = []

    def add(message: str, level: str = "INFO", stage: str = "boot") -> None:
        lines.append(
            {
                "seq": SEQ_OFFSET + len(lines) + 1,
                "level": level,
                "stage": stage,
                "message": str(message)[:4000],
            }
        )

    add(f"onstart mulai: task={TASK_ID or '<kosong>'} role={os.environ.get('CLIPZI_ROLE', '')}")

    # --- Env penting (jangan cetak nilai rahasia) ---
    baked = (os.environ.get("CLIPZI_MODEL_SOURCE") or "").lower() == "baked"
    for name in (
        "DATABASE_URL",
        "ENCRYPTION_KEY",
        "SECRET_KEY",
        "CLIPZI_CALLBACK_URL",
        "CLIPZI_WORKER_TOKEN",
        "R2_BUCKET_NAME",
        "YTDLP_PROXY",
        "YTDLP_COOKIES_BASE64",
        "YTDLP_COOKIES_GZIP_B64",
        "YTDLP_COOKIES_MISSING",
        "GPU_WHISPER_MODEL",
        "CLIPZI_MODEL_SOURCE",
        "CLIPZI_MODEL_URL",
        "CLIPZI_HF_REPO",
    ):
        value = os.environ.get(name)
        if value:
            add(f"env {name}=<set> ({len(value)} char)")
            continue
        # Cookies dipadatkan ke gzip saat > 4 KB: BASE64 kosong itu NORMAL.
        if name == "YTDLP_COOKIES_BASE64" and os.environ.get("YTDLP_COOKIES_GZIP_B64"):
            add("env YTDLP_COOKIES_BASE64=<dipadatkan ke YTDLP_COOKIES_GZIP_B64>")
            continue
        # Model sudah dibekukan di image: URL/HF repo memang tidak dikirim.
        if baked and name in ("CLIPZI_MODEL_URL", "CLIPZI_HF_REPO"):
            add(f"env {name}=<tidak perlu: model baked di image>")
            continue
        add(f"env {name}=<kosong>", level="WARN")

    # --- GPU ---
    if shutil.which("nvidia-smi"):
        gpu = _run(
            "nvidia-smi --query-gpu=name,memory.total,driver_version "
            "--format=csv,noheader"
        )
        add(f"GPU: {gpu or 'nvidia-smi tanpa keluaran'}", level="INFO" if gpu else "WARN")
    else:
        add("nvidia-smi tidak tersedia (GPU mungkin tidak terpasang)", level="WARN")

    # --- Model Whisper ---
    # Path model mengikuti env worker (baked: /app/whisper_model). Fallback ke
    # /workspace/whisper_model untuk instance lama yang me-restore model.
    model_dir = (
        os.environ.get("GPU_WHISPER_MODEL")
        or os.environ.get("CLIPZI_RESTORE_MODEL_PATH")
        or "/app/whisper_model"
    )
    if not os.path.isdir(model_dir) and os.path.isdir("/workspace/whisper_model"):
        model_dir = "/workspace/whisper_model"
    if os.path.isdir(model_dir):
        try:
            files = sorted(os.listdir(model_dir))[:8]
        except OSError:
            files = []
        add(f"model dir {model_dir}: {', '.join(files) if files else '<kosong>'}")
    else:
        add(f"model dir {model_dir} belum ada", level="WARN")

    # --- Disk & memori ---
    add(f"disk: {_run('df -h / | tail -1') or '-'}")
    add(f"memori: {_run('free -m | head -2 | tail -1') or '-'}")

    # --- bgutil PO token provider ---
    if os.path.exists("/opt/bgutil/server/build/main.js"):
        add("bgutil provider tersedia di image")
    else:
        add("bgutil provider tidak ada di image (fallback cookies/proxy)", level="WARN")

    add("onstart probe selesai; pipeline belum dijalankan")
    return lines


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        return 0

    if argv[0] == "--probe":
        lines = _probe_lines()
        _post(lines)
        # Cetak juga ke stdout container supaya terlihat di `docker logs`.
        for line in lines:
            print(f"[onstart] {line['level']} {line['message']}", flush=True)
        return 0

    message = argv[0]
    level = "INFO"
    stage = "boot"
    index = 1
    while index < len(argv):
        if argv[index] == "--level" and index + 1 < len(argv):
            level = argv[index + 1].upper()
            index += 2
        elif argv[index] == "--stage" and index + 1 < len(argv):
            stage = argv[index + 1]
            index += 2
        else:
            index += 1

    _post(
        [
            {
                "seq": SEQ_OFFSET + 1,
                "level": level[:16],
                "stage": stage[:40],
                "message": str(message)[:20000],
            }
        ]
    )
    print(f"[onstart] {level} {message}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
