#!/bin/sh
# =============================================================================
# Entrypoint image backend Clipzi AI.
#
# Satu image dipakai untuk dua peran:
#   CLIPZI_ROLE=api    (default) -> uvicorn app.main:app        (REST API)
#   CLIPZI_ROLE=worker           -> uvicorn deployments.worker_api:app (GPU worker)
#
# Contoh menjalankan worker (Vast.ai launch_args):
#   --env '-e CLIPZI_ROLE=worker' --env '-e WORKER_PORT=8000'
# =============================================================================
set -eu

ROLE="${CLIPZI_ROLE:-api}"
PORT_TO_USE="${PORT:-8000}"

echo "[entrypoint] role=${ROLE} port=${PORT_TO_USE}"

if [ "$ROLE" = "worker" ]; then
    PORT_TO_USE="${WORKER_PORT:-$PORT_TO_USE}"
    echo "[entrypoint] menjalankan GPU worker di port ${PORT_TO_USE}"
    exec uvicorn deployments.worker_api:app \
        --host 0.0.0.0 \
        --port "$PORT_TO_USE" \
        --proxy-headers \
        --forwarded-allow-ips '*'
fi

echo "[entrypoint] menjalankan REST API di port ${PORT_TO_USE}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT_TO_USE" \
    --proxy-headers \
    --forwarded-allow-ips '*'
