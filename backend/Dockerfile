# syntax=docker/dockerfile:1
# =============================================================================
# Clipzi AI - Backend (FastAPI) production image
# Build : docker build -t <dockerhub-user>/clipzi-backend:latest -f backend/Dockerfile backend
# Run   : docker run -p 8000:8000 --env-file backend/.env <image>
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: build Python dependencies ke dalam virtualenv terisolasi
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Toolchain untuk paket yang belum punya wheel siap pakai
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2: runtime image (tanpa toolchain, ukuran lebih kecil)
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:/opt/venv/bin:$PATH" \
    APP_HOME=/app

# Library sistem:
#   ffmpeg              -> cut/render video & ekstraksi audio
#   libgl1, libglib2.0  -> OpenCV (opencv-python)
#   libsndfile1         -> faster-whisper / soundfile
#   libgomp1            -> ctranslate2 (engine faster-whisper)
#   libfontconfig1      -> render teks/caption
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libfontconfig1 \
    libsndfile1 \
    libgomp1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp standalone versi terbaru. Ditaruh di /usr/local/bin yang ada di depan
# /opt/venv/bin pada PATH agar versi ini yang dipakai (YouTube sering berubah).
RUN curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
      -o /usr/local/bin/yt-dlp \
    && chmod 0755 /usr/local/bin/yt-dlp

# Ambil virtualenv dari stage builder
COPY --from=builder /opt/venv /opt/venv

WORKDIR $APP_HOME
COPY . .

# Jalankan sebagai user non-root
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin clipzi \
    && mkdir -p $APP_HOME/media $APP_HOME/tmp \
    && chown -R clipzi:clipzi $APP_HOME

EXPOSE 8000

# /api/health selalu balas 200 (status healthy/degraded), cocok untuk liveness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-8000}/api/health || exit 1

# Entrypoint memilih peran berdasarkan CLIPZI_ROLE:
#   api (default) -> uvicorn app.main:app
#   worker        -> uvicorn deployments.worker_api:app   (GPU worker Vast.ai)
COPY --chown=clipzi:clipzi docker-entrypoint.sh /usr/local/bin/clipzi-entrypoint.sh
RUN chmod 0755 /usr/local/bin/clipzi-entrypoint.sh

USER clipzi
ENTRYPOINT ["/usr/local/bin/clipzi-entrypoint.sh"]