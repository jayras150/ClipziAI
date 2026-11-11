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
# Stage 2 (opsional): dependency GPU untuk WORKER
#
# Hanya dipakai target `worker` (Vast.ai serverless). VPS memakai target `api`
# yang LEAN — tanpa lib CUDA dan tanpa Whisper — supaya beban berat tidak pernah
# menyentuh server hosting backend/frontend.
#
# Mesin transkripsi: CTranslate2 (faster-whisper) + cuBLAS/cuDNN dari paket pip
# (±1,5 GB), bukan torch (±3 GB). Model TIDAK dibaking; diunduh per instance
# Vast (large-v3 ±3 GB, atau set GPU_WHISPER_MODEL=turbo untuk ±1,6 GB).
# -----------------------------------------------------------------------------
FROM builder AS builder-worker

COPY requirements-gpu-whisper.txt ./
RUN pip install -r requirements-gpu-whisper.txt && \
    python -c "import faster_whisper, ctranslate2; print('ct2', ctranslate2.__version__, 'gpu libs siap')"

# -----------------------------------------------------------------------------
# Stage 2b: dependency Whisper CPU untuk TARGET `api`
#
# API ikut men-transkripsi klip lama (belum punya transkrip pipeline / SRT)
# supaya metadata AI tetap bisa dibuat walau provider transkripsi berbasis API
# kehabisan kredit. Model Whisper TIDAK dibaking; diunduh saat runtime ke
# HF_HOME (volume cache) dan dipakai ulang pada request berikutnya.
# -----------------------------------------------------------------------------
FROM builder AS builder-api-whisper

COPY requirements-whisper-cpu.txt ./
RUN pip install -r requirements-whisper-cpu.txt && \
    python -c "import faster_whisper; print('faster-whisper siap (cpu)')"

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

# Data model deteksi wajah (auto zoom follow-speaker).
# OpenCV 5.x menghapus cv2.CascadeClassifier dan tidak lagi membundel file XML
# haar, sehingga dipakai model ONNX YuNet yang diunduh saat build.
RUN mkdir -p /opt/opencv-data \
    && curl -fsSL -o /opt/opencv-data/face_detection_yunet_2023mar.onnx \
       https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
    && ls -l /opt/opencv-data \
    && test "$(stat -c%s /opt/opencv-data/face_detection_yunet_2023mar.onnx)" -gt 100000

# Ambil virtualenv: dipindah ke masing-masing TARGET (api/worker) karena
# keduanya memakai builder berbeda (worker menambah lib CUDA + Whisper).

WORKDIR $APP_HOME
COPY . .

# Jalankan sebagai user non-root
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin clipzi \
    && mkdir -p $APP_HOME/media $APP_HOME/tmp \
    && chown -R clipzi:clipzi $APP_HOME

EXPOSE 8000

# Healthcheck harus sadar peran:
#   api                     -> /api/health di PORT (8000)
#   worker (PyWorker)       -> /health di MODEL_SERVER_PORT (pipeline), karena
#                              port WORKER_PORT dipakai PyWorker (tanpa /api/health)
#   worker (mode api lokal) -> /health di WORKER_PORT
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD if [ "${CLIPZI_ROLE:-api}" != "worker" ]; then \
          curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health"; \
        elif [ "${CLIPZI_WORKER_MODE:-pyworker}" = "api" ]; then \
          curl -fsS "http://127.0.0.1:${WORKER_PORT:-8000}/health"; \
        else \
          curl -fsS "http://127.0.0.1:${MODEL_SERVER_PORT:-18000}/health"; \
        fi

# Entrypoint memilih peran berdasarkan CLIPZI_ROLE:
#   api (default) -> uvicorn app.main:app
#   worker        -> PyWorker (port WORKER_PORT) + uvicorn deployments.worker_api:app
#                    di 127.0.0.1:MODEL_SERVER_PORT (lihat deployments/pyworker_main.py)
#
# Bit executable dipasang lewat --chmod (didukung BuildKit) agar tidak perlu
# langkah `RUN chmod` tambahan yang bisa gagal bila path berubah.
COPY --chown=clipzi:clipzi --chmod=0755 docker-entrypoint.sh /usr/local/bin/clipzi-entrypoint.sh
COPY --chown=clipzi:clipzi --chmod=0755 deployments/pipeline_onstart.sh deployments/pipeline_onstart.sh

USER clipzi
ENTRYPOINT ["/usr/local/bin/clipzi-entrypoint.sh"]

# =============================================================================
# TARGET "api" — untuk VPS (hosting backend + frontend).
#
# Whisper CPU (faster-whisper int8) ikut dipasang karena API perlu men-transkripsi
# klip lama yang belum punya transkrip/ SRT agar metadata AI tetap bisa dibuat
# tanpa kredit provider. Tanpa lib CUDA dan tanpa model yang dibaking, jadi
# tambahan image ±250 MB dan model diunduh ke volume cache saat pertama dipakai.
# Render video berat tetap hanya di worker Vast.ai.
# =============================================================================
FROM runtime AS api

COPY --from=builder-api-whisper /opt/venv /opt/venv

# =============================================================================
# Model GGUF (Qwen3-4B-Instruct-2507) — stage terpisah TANPA ketergantungan kode.
#
# Kenapa dipisah: kalau unduhan 2,55 GB ada di stage `worker` (setelah `COPY . .`),
# setiap perubahan kode membatalkan cache layer tersebut sehingga build ulang
# mengunduh model lagi (build 7-19 menit). Stage ini cache-nya stabil.
# =============================================================================
FROM python:3.11-slim AS gguf
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && mkdir -p /models \
    && curl -fsSL -o /models/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf \
       https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf \
    && test "$(stat -c%s /models/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf)" -gt 2000000000 \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Image resmi llama.cpp (CUDA) — hanya diambil binernya untuk LLM lokal.
# =============================================================================
FROM ghcr.io/ggml-org/llama.cpp:server-cuda AS llama

# =============================================================================
# TARGET "worker" — untuk Vast.ai serverless (GPU).
#
# Menambah Whisper (CTranslate2 large-v3) + lib CUDA. Tag inilah yang dipakai
# VAST_WORKER_IMAGE. Model Whisper diunduh saat runtime ke cache HF milik user
# container (HOME=/home/clipzi), jadi tidak perlu dibaking ke image.
# =============================================================================
FROM runtime AS worker

# Vast.ai menaruh launcher-nya sendiri di `/.launch` di dalam instance. Pada
# sebagian tipe instance launcher itu memanggil `ssh` / `ssh-keygen` / `sshd`
# (akses SSH & reverse tunnel) — base image python:slim tidak punya OpenSSH,
# sehingga muncul loop `/.launch: line 48: ssh: command not found` dan pipeline
# tidak pernah jalan. Pasang client + server supaya launcher tidak gagal.
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        openssh-server \
    && mkdir -p /run/sshd \
    && rm -rf /var/lib/apt/lists/* \
    && ssh -V \
    && command -v sshd
USER clipzi

COPY --from=builder-worker /opt/venv /opt/venv

# Worker = GPU. Transkripsi dijalankan di GPU (faster-whisper CUDA float16)
# supaya video panjang selesai dalam hitungan menit, bukan puluhan menit di CPU,
# dan timestamp per kata lebih akurat untuk pemotongan klip.
# `large-v3` = model openai/whisper-large-v3 (CTranslate2).
ENV TRANSCRIPTION_PROVIDER="gpu" \
    GPU_WHISPER_MODEL="large-v3" \
    TRANSCRIPTION_ALLOW_REMOTE="false"

# ---------------------------------------------------------------------------
# LLM lokal: llama.cpp server (CUDA) + Qwen3-4B-Instruct-2507 (GGUF Q4_K_XL).
# Semua analisis AI (rerank momen viral, skor, judul/deskripsi/tag) berjalan di
# instance ini — tidak ada audio/teks yang dikirim ke provider luar.
# ---------------------------------------------------------------------------
COPY --from=llama /app /opt/llama
ENV PATH="/opt/llama:${PATH}"
# libggml*/libllama*.so ada di /opt/llama; tanpa entri ini llama-server gagal
# start dengan "error while loading shared libraries".
ENV LD_LIBRARY_PATH="/opt/llama:/opt/venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.11/site-packages/nvidia/cudnn/lib:/opt/venv/lib/python3.11/site-packages/nvidia/cuda_runtime/lib:${LD_LIBRARY_PATH}"
ENV AI_PROVIDER="custom" \
    AI_BASE_URL="http://127.0.0.1:8080/v1" \
    AI_MODEL="Qwen3-4B-Instruct-2507"

USER root
COPY --from=gguf /models /app/models
RUN test "$(stat -c%s /app/models/Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf)" -gt 2000000000 \
    && chown -R clipzi:clipzi /app/models \
    && /opt/llama/llama-server --version || true
USER clipzi


ENV LD_LIBRARY_PATH="/opt/venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.11/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}"