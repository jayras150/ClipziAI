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

if [ -z "${CLIPZI_TASK_ID:-}" ]; then
    echo "[onstart] CLIPZI_TASK_ID kosong; tidak ada yang dikerjakan" >&2
    exit 2
fi

cd /app || exit 1
PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python"

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
    },
)
try:
    urllib.request.urlopen(request, timeout=10).read()
    print("[onstart] callback boot terkirim", flush=True)
except Exception as exc:
    print(f"[onstart] callback boot gagal: {exc}", flush=True)
PY
fi

echo "[onstart] menjalankan pipeline untuk task ${CLIPZI_TASK_ID} (python: ${PYTHON_BIN})"

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
