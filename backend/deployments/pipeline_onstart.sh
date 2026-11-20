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

# --- Log onstart SEBELUM pipeline/download apa pun ---------------------------
# Admin harus bisa melihat kondisi instance (env, GPU, model, disk) sejak detik
# pertama, bukan menunggu pipeline berjalan. `onstart_log.py --probe` mengirim
# ringkasan ke POST /api/internal/worker/logs dan mencetaknya ke stdout.
# Jumlah baris probe dipakai sebagai offset seq shipper supaya tidak bentrok.
ONSTART_LOG_LINES=0
if [ -f /app/deployments/onstart_log.py ]; then
    ONSTART_LOG_LINES=$("$PYTHON_BIN" -u /app/deployments/onstart_log.py --probe 2>/dev/null | grep -c '^\[onstart\]' || true)
    [ -n "$ONSTART_LOG_LINES" ] || ONSTART_LOG_LINES=0
    export CLIPZI_LOG_SEQ_OFFSET="$ONSTART_LOG_LINES"
    log "log onstart terkirim (${ONSTART_LOG_LINES} baris); pipeline belum dijalankan"
else
    log "onstart_log.py tidak ada di image; log awal dilewati"
fi

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
# --- Restore model dari provider non-Drive (Dropbox / B2 / S3 / HuggingFace) -
# Backend mengirim CLIPZI_MODEL_URL (tautan unduh model.bin) atau CLIPZI_HF_REPO
# sehingga worker tidak perlu menunggu cloud_copy Vast yang khusus Google Drive.
# --- Cookies YouTube via API (bukan env) ------------------------------------
# Cookies TIDAK lagi dikirim lewat env Vast (batas env ±4 KB, dan metadata
# instance Vast bisa dibaca dari dashboard). Worker mengambil cookies.txt aktif
# langsung dari API memakai token yang sama dengan callback. Gagal = tidak
# fatal: pipeline masih memakai pool tabel ytdlp_cookies lewat DATABASE_URL.
CLIPZI_COOKIE_FILE=/tmp/ytdlp_cookies.txt
if [ -n "${CLIPZI_API_BASE:-}" ] && [ -n "${CLIPZI_WORKER_TOKEN:-}" ]; then
    if curl -fsS --max-time 15 \
        -H "x-clipzi-token: ${CLIPZI_WORKER_TOKEN}" \
        -o "$CLIPZI_COOKIE_FILE" \
        "${CLIPZI_API_BASE}/api/internal/cookies/active.txt" 2>/dev/null \
        && [ -s "$CLIPZI_COOKIE_FILE" ]; then
        export YTDLP_COOKIES_FILE="$CLIPZI_COOKIE_FILE"
        log "cookies: via api ($(wc -c < "$CLIPZI_COOKIE_FILE" | tr -d ' ') byte)"
    else
        rm -f "$CLIPZI_COOKIE_FILE"
        log "cookies: api tidak memberi cookies; fallback ke pool database"
    fi
else
    log "cookies: CLIPZI_API_BASE/CLIPZI_WORKER_TOKEN kosong; fallback ke pool database"
fi

log "menjalankan pipeline untuk task ${CLIPZI_TASK_ID} (python: ${PYTHON_BIN})"

# Catat titik mulai pipeline ke dashboard (setelah bgutil & model siap).
if [ -f /app/deployments/onstart_log.py ]; then
    "$PYTHON_BIN" -u /app/deployments/onstart_log.py \
        "pipeline dimulai (bgutil & model siap); download/render berikutnya" \
        --stage boot --level INFO >/dev/null 2>&1 || true
fi

exec "$PYTHON_BIN" -u /app/deployments/worker_log_shipper.py -- "$PYTHON_BIN" -u -c '
import asyncio
import os
from uuid import UUID

from app.services.pipeline import run_video_pipeline

task_id = UUID(os.environ["CLIPZI_TASK_ID"])
result = asyncio.run(run_video_pipeline(task_id))
print("PIPELINE_RESULT", result, flush=True)
raise SystemExit(0 if result.get("ok") else 1)
'
