#!/bin/sh
# =============================================================================
# Entrypoint image backend Clipzi AI.
#
# Satu image dipakai untuk dua peran:
#   CLIPZI_ROLE=api    (default) -> uvicorn app.main:app        (REST API)
#   CLIPZI_ROLE=worker           -> PyWorker + uvicorn deployments.worker_api:app
#
# Peran worker WAJIB memakai PyWorker: hanya PyWorker yang melapor `ready` ke
# router Vast.ai. Port publik container adalah WORKER_PORT (PyWorker), sedangkan
# service pipeline berjalan di localhost:MODEL_SERVER_PORT.
#
# Contoh menjalankan worker (Vast.ai template env):
#   -p 8000:8000 -e CLIPZI_ROLE=worker -e WORKER_PORT=8000 -e MODEL_SERVER_PORT=18000
#
# Untuk uji lokal tanpa Vast (tanpa PyWorker):
#   CLIPZI_ROLE=worker CLIPZI_WORKER_MODE=api docker run ... (uvicorn langsung)
# =============================================================================
set -eu

ROLE="${CLIPZI_ROLE:-api}"
PORT_TO_USE="${PORT:-8000}"

echo "[entrypoint] role=${ROLE} port=${PORT_TO_USE}"

if [ "$ROLE" = "worker" ]; then
    # PO-token provider (bgutil) WAJIB hidup: tanpa ini YouTube hanya memberi
    # storyboard untuk banyak video (format video tidak tersedia).
    if [ -f /opt/bgutil/server/build/main.js ]; then
        mkdir -p /app/tmp 2>/dev/null || true
        (cd /opt/bgutil/server && node build/main.js \
            >"${POT_PROVIDER_LOG:-/app/tmp/pot-provider.log}" 2>&1 &) || true
        echo "[entrypoint] PO token provider (bgutil) dijalankan di :4416"
    fi
    if [ "${CLIPZI_WORKER_MODE:-pyworker}" = "api" ]; then
        PORT_TO_USE="${WORKER_PORT:-$PORT_TO_USE}"
        echo "[entrypoint] GPU worker (mode api, tanpa PyWorker) di port ${PORT_TO_USE}"
        exec uvicorn deployments.worker_api:app \
            --host 0.0.0.0 \
            --port "$PORT_TO_USE" \
            --proxy-headers \
            --forwarded-allow-ips '*'
    fi

    export WORKER_PORT="${WORKER_PORT:-8000}"
    export MODEL_SERVER_PORT="${MODEL_SERVER_PORT:-18000}"
    # Harus bisa DIBACA oleh PyWorker (deteksi "Application startup complete.").
    # /app/tmp sudah ada dan dimiliki user non-root image ini.
    export MODEL_LOG_FILE="${MODEL_LOG_FILE:-/app/tmp/model-server.log}"
    # PENTING: `python` di PATH runtime adalah /usr/local/bin/python (python
    # sistem) sedangkan dependency dipasang di /opt/venv. Tanpa path eksplisit,
    # PyWorker gagal: "ModuleNotFoundError: No module named 'vastai'".
    PYTHON_BIN="${PYTHON_BIN:-/opt/venv/bin/python}"
    [ -x "$PYTHON_BIN" ] || PYTHON_BIN="python"
    echo "[entrypoint] GPU worker (PyWorker) di port ${WORKER_PORT};" \
         "pipeline di 127.0.0.1:${MODEL_SERVER_PORT} (python: ${PYTHON_BIN})"
    exec "$PYTHON_BIN" -u -m deployments.pyworker_main
fi

echo "[entrypoint] menjalankan REST API di port ${PORT_TO_USE}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT_TO_USE" \
    --proxy-headers \
    --forwarded-allow-ips '*'


echo "[entrypoint] menjalankan REST API di port ${PORT_TO_USE}"
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT_TO_USE" \
    --proxy-headers \
    --forwarded-allow-ips '*'
