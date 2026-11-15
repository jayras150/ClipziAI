#!/bin/sh
# =============================================================================
# Onstart untuk instance Vast.ai mode "oneshot": jalankan SATU task lalu keluar.
#
# Kenapa file ini ada: Vast mengeksekusi `--onstart-cmd` sebagai perintah exec
# (tanpa shell). String seperti `cd /app && python -c '...'` gagal dengan:
#   exec: "cd /app && python -c ...": no such file or directory
# Jadi kita kirim path script ini saja, dan task id lewat environment variable.
#
#   --onstart-cmd /app/deployments/pipeline_onstart.sh
#   --env '-e CLIPZI_TASK_ID=<uuid> -e CLIPZI_ROLE=worker'
# =============================================================================
set -eu

# -----------------------------------------------------------------------------
# Diagnostik & validasi task id
#
# PENTING: kalau CLIPZI_TASK_ID kosong, jangan mati tanpa jejak. Instance dari
# template (dibuat manual di dashboard Vast) memang tidak punya task id; dulu
# script keluar exit 2 sehingga instance tampak "hidup" dengan CPU/GPU 0% dan
# admin bingung. Sekarang semua kondisi dicetak ke log instance.
# -----------------------------------------------------------------------------
log() { echo "[onstart] $*"; }

# Binary python harus ditentukan SEBELUM dipakai (set -u akan abort bila kosong).
cd /app 2>/dev/null || true
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python"

TASK_ID="${CLIPZI_TASK_ID:-}"
log "start task=${TASK_ID:-<kosong>} role=${CLIPZI_ROLE:-} at=$(date -u +%FT%TZ)"

if [ -z "$TASK_ID" ]; then
    log "CLIPZI_TASK_ID kosong. Env terdeteksi:"
    log "  DATABASE_URL=${DATABASE_URL:+<set>} ENCRYPTION_KEY=${ENCRYPTION_KEY:+<set>} SECRET_KEY=${SECRET_KEY:+<set>}"
    log "  CLIPZI_CALLBACK_URL=${CLIPZI_CALLBACK_URL:+<set>} CLIPZI_WORKER_TOKEN=${CLIPZI_WORKER_TOKEN:+<set>}"
    log "  GPU_WHISPER_MODEL=${GPU_WHISPER_MODEL:-} CLIPZI_RESTORE_MODEL_PATH=${CLIPZI_RESTORE_MODEL_PATH:-}"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
    else
        log "nvidia-smi tidak tersedia"
    fi
    ls -la /workspace 2>/dev/null | head -20 || log "/workspace tidak bisa dibaca"
    if [ "${CLIPZI_ALLOW_MANUAL:-0}" = "1" ]; then
        log "CLIPZI_ALLOW_MANUAL=1: instance dibiarkan hidup untuk inspeksi; pipeline tidak dijalankan."
        exit 0
    fi
    log "Keluar: set CLIPZI_TASK_ID (dikirim backend saat dispatch) atau CLIPZI_ALLOW_MANUAL=1 untuk tes manual."
    exit 2
fi

# Mode probe: verifikasi env/GPU/model tanpa menjalankan pipeline (biaya minimal).
if [ "${CLIPZI_PROBE:-0}" = "1" ]; then
    log "PROBE mode: env & runtime check"
    log "  task_id=$TASK_ID"
    log "  GPU_WHISPER_MODEL=${GPU_WHISPER_MODEL:-}"
    log "  model_dir=${CLIPZI_RESTORE_MODEL_PATH:-/workspace/whisper_model}"
    ls -la "${CLIPZI_RESTORE_MODEL_PATH:-/workspace/whisper_model}" 2>/dev/null | head -10 || log "  model_dir belum ada"
    if command -v nvidia-smi >/dev/null 2>&1; then
        nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true
    fi
    "$PYTHON_BIN" - <<'PY' || true
import os
keys = sorted(k for k in os.environ if k.startswith(("CLIPZI_", "DATABASE_URL", "ENCRYPTION_KEY", "SECRET_KEY", "GPU_", "TRANSCRIPTION_", "YTDLP_")))
print("[onstart] PROBE env keys:", ",".join(keys))
print("[onstart] PROBE task id:", os.environ.get("CLIPZI_TASK_ID"))
print("[onstart] PROBE marker:", os.environ.get("CLIPZI_PROBE_MARKER"))
PY
    log "PROBE selesai; instance boleh dihapus."
    exit 0
fi

cd /app || exit 1

# --- Callback "boot" ke API (webhook milik kita; Vast tidak punya webhook) -----
# Supervisor instance memakai sinyal ini untuk membedakan "container hidup" dari
# "instance running tapi onstart tidak pernah jalan". Kegagalan diabaikan.
if [ -n "${CLIPZI_CALLBACK_URL:-}" ] && [ -n "${CLIPZI_WORKER_TOKEN:-}" ]; then
    "$PYTHON_BIN" - <<'PY' || true
import hashlib
import hmac
import json
import os
import urllib.request

body = json.dumps(
    {"task_id": os.environ["CLIPZI_TASK_ID"], "event": "boot"},
    separators=(",", ":"),
).encode()
signature = hmac.new(
    os.environ["CLIPZI_WORKER_TOKEN"].encode(), body, hashlib.sha256
).hexdigest()
request = urllib.request.Request(
    os.environ["CLIPZI_CALLBACK_URL"],
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Clipzi-Signature": "sha256=" + signature,
        # Cloudflare memblokir User-Agent default urllib (error 1010/403).
        "User-Agent": "ClipziAI-Worker/1.0",
    },
)
try:
    urllib.request.urlopen(request, timeout=10).read()
    print("[onstart] callback boot terkirim", flush=True)
except Exception as exc:
    print(f"[onstart] callback boot gagal: {exc}", flush=True)
PY
fi

# --- PO token provider (bgutil) -------------------------------------------
# Plugin `youtubepot-bgutilhttp` otomatis memakai http://127.0.0.1:4416, jadi
# cukup jalankan server-nya. Kalau gagal, pipeline tetap lanjut (fallback ke
# cookies / proxy) daripada menggagalkan task.
if [ -f /opt/bgutil/server/build/main.js ] && command -v node >/dev/null 2>&1; then
    node /opt/bgutil/server/build/main.js --port 4416 --host 127.0.0.1 \
        >> /tmp/bgutil-provider.log 2>&1 &
    "$PYTHON_BIN" - <<'PY' || true
import socket
import time

for _ in range(30):
    try:
        with socket.create_connection(("127.0.0.1", 4416), timeout=1):
            print("[onstart] bgutil PO token provider siap", flush=True)
            break
    except OSError:
        time.sleep(1)
else:
    print("[onstart] bgutil provider tidak siap; lanjut tanpa PO token", flush=True)
PY
else
    echo "[onstart] bgutil provider tidak ada di image; lanjut tanpa PO token"
fi

# --- Restore model Whisper dari Google Drive --------------------------------
# Model disalin backend lewat `cloud_copy` Cloud→Instance SETELAH instance dibuat.
# Kalau path salah / copy gagal, jangan menunggu 900 s dengan CPU/GPU 0%: setelah
# `CLIPZI_RESTORE_FAST_FAIL` detik tanpa model, cetak isi folder lalu unduh model.
if [ -n "${CLIPZI_RESTORE_TIMEOUT:-}" ]; then
    RESTORE_PATH="${CLIPZI_RESTORE_MODEL_PATH:-/workspace/whisper_model}"
    FAST_FAIL="${CLIPZI_RESTORE_FAST_FAIL:-150}"
    # Kalau cloud copy SUDAH menaruh model (walau read-only milik root), pakai
    # langsung: membaca tidak butuh izin tulis. Dulu script pindah ke folder
    # kosong lalu mengunduh ulang 3 GB -> lambat + disk penuh.
    EXISTING_MODEL="$(find "$RESTORE_PATH" -maxdepth 2 -name model.bin -type f 2>/dev/null | head -n 1)"
    if [ -n "$EXISTING_MODEL" ]; then
        MODEL_PATH="$(dirname "$EXISTING_MODEL")"
        log "model restore ditemukan: $EXISTING_MODEL (read-only tidak masalah)"
    else
        MODEL_PATH="$RESTORE_PATH"
        mkdir -p "$MODEL_PATH" 2>/dev/null || true
        if [ ! -w "$MODEL_PATH" ]; then
            MODEL_PATH="/app/whisper_model"
            mkdir -p "$MODEL_PATH" 2>/dev/null || true
            log "PERINGATAN: $RESTORE_PATH tidak writable dan model belum ada; unduh ke $MODEL_PATH"
        fi
    fi
    export GPU_WHISPER_MODEL="$MODEL_PATH"
    export HF_HOME="${HF_HOME:-/app/.cache/huggingface}"
    started=$(date +%s)
    deadline=$(( started + CLIPZI_RESTORE_TIMEOUT ))
    fast_deadline=$(( started + FAST_FAIL ))
    prev_size=""
    stable=0
    last_log=0
    log "menunggu model di ${MODEL_PATH} (timeout ${CLIPZI_RESTORE_TIMEOUT}s, fast-fail ${FAST_FAIL}s)"
    while :; do
        now=$(date +%s)
        if [ -f "$MODEL_PATH/model.bin" ]; then
            size=$(wc -c < "$MODEL_PATH/model.bin" 2>/dev/null | tr -d ' ' || echo 0)
            if [ "$size" = "$prev_size" ] && [ "${size:-0}" -gt 100000000 ]; then
                stable=$((stable + 1))
            else
                stable=0
            fi
            prev_size="$size"
            if [ "$stable" -ge 2 ]; then
                log "restore selesai (${size} byte)"
                break
            fi
        elif [ "$now" -ge "$fast_deadline" ]; then
            log "model belum ada setelah ${FAST_FAIL}s; isi ${MODEL_PATH}:"
            ls -la "$MODEL_PATH" 2>/dev/null | head -12 || log "  folder ${MODEL_PATH} tidak ada"
            log "fallback unduh model large-v3 (butuh ±3 GB; disk harus cukup)"
            "$PYTHON_BIN" - <<PY || true
from faster_whisper.utils import download_model
download_model("large-v3", output_dir="$MODEL_PATH")
PY
            break
        fi
        if [ $(( now - last_log )) -ge 30 ]; then
            log "menunggu model: ${prev_size:-0} byte, sisa $(( deadline - now ))s"
            last_log=$now
        fi
        if [ "$now" -ge "$deadline" ]; then
            log "restore timeout; fallback unduh model"
            "$PYTHON_BIN" - <<PY || true
from faster_whisper.utils import download_model
download_model("large-v3", output_dir="$MODEL_PATH")
PY
            break
        fi
        sleep 10
    done
fi

log "menjalankan pipeline untuk task ${CLIPZI_TASK_ID} (python: ${PYTHON_BIN})"

exec "$PYTHON_BIN" -u -c '
import asyncio
import os
from uuid import UUID

from app.services.pipeline import run_video_pipeline

task_id = UUID(os.environ["CLIPZI_TASK_ID"])
result = asyncio.run(run_video_pipeline(task_id))
print("PIPELINE_RESULT", result, flush=True)
raise SystemExit(0 if result.get("ok") else 1)
'
