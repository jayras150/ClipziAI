#!/usr/bin/env python3
"""Entrypoint pipeline worker: konfigurasi logging + diagnostik device.

Kenapa file ini ada: `pipeline_onstart.sh` dulu menjalankan `python -u -c
'from app.services.pipeline import run_video_pipeline; ...'`. Proses itu tidak
melewati `app.main`, sehingga `logging.basicConfig()` tidak pernah dipanggil dan
root logger memakai default WARNING. Akibatnya SEMUA `logger.info` penting —
device Whisper (`device=cuda`/`cpu`), encoder (`h264_nvenc`/`libx264`), backend
YOLO, dan durasi tiap stage — tidak pernah ditulis ke stdout, sehingga shipper
tidak bisa mengirimnya ke admin. Yang tampil hanya output yt-dlp.

Di sini logging dipasang SEBELUM import pipeline, lalu device yang benar-benar
terdeteksi dicetak sekali di awal supaya CPU-vs-GPU tidak perlu ditebak.
"""
import asyncio
import logging
import os
import sys
from uuid import UUID

# PENTING: script ini ada di /app/deployments, dan folder itu juga berisi
# `app.py` (file). Bila folder itu ada di sys.path, `import app...` menemukan
# `/app/deployments/app.py` dan gagal dengan
#   "No module named 'app.core'; 'app' is not a package"
# (terbukti di Vast: exit=1 dalam 0 detik).
#
# `if _APP_ROOT not in sys.path` TIDAK cukup: /app sudah ada di sys.path
# (dari PYTHONPATH) tapi di belakang, sehingga folder script tetap menang.
# Karena itu folder script dibuang dari sys.path dan /app dipaksa paling depan.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path[:] = [
    path
    for path in sys.path
    if os.path.abspath(path or os.getcwd()) != _SCRIPT_DIR
]
while _APP_ROOT in sys.path:
    sys.path.remove(_APP_ROOT)
sys.path.insert(0, _APP_ROOT)


def _setup_logging() -> None:
    level = (os.environ.get("CLIPZI_LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Logger pihak ketiga yang terlalu berisik pada level INFO.
    for noisy in ("yt_dlp", "urllib3", "botocore", "boto3", "s3transfer", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _log_runtime() -> None:
    """Cetak device aktual: ini yang dipakai untuk membuktikan GPU vs CPU."""
    log = logging.getLogger("clipzi.runtime")

    cuda_devices = None
    try:
        import ctranslate2  # dipakai faster-whisper

        cuda_devices = int(ctranslate2.get_cuda_device_count())
        log.info("ctranslate2: cuda_devices=%s", cuda_devices)
    except Exception as exc:  # noqa: BLE001
        log.warning("ctranslate2 tidak bisa dipakai (GPU Whisper mati): %s", exc)

    try:
        import onnxruntime as ort

        providers = list(ort.get_available_providers())
        log.info("onnxruntime %s: providers=%s", ort.__version__, ",".join(providers))
        if "CUDAExecutionProvider" not in providers:
            log.warning(
                "ONNX tidak melihat CUDAExecutionProvider — deteksi person akan "
                "memakai CPU (pasang onnxruntime-gpu di image worker)."
            )
    except Exception as exc:  # noqa: BLE001
        log.info("onnxruntime tidak tersedia: %s", exc)

    log.info(
        "env: TRANSCRIPTION_PROVIDER=%s ALLOW_REMOTE=%s FFMPEG_ENCODER=%s "
        "GPU_WHISPER_MODEL=%s",
        os.environ.get("TRANSCRIPTION_PROVIDER") or "-",
        os.environ.get("TRANSCRIPTION_ALLOW_REMOTE") or "-",
        os.environ.get("FFMPEG_ENCODER") or "-",
        os.environ.get("GPU_WHISPER_MODEL") or "-",
    )
    if cuda_devices == 0:
        log.error(
            "GPU TIDAK TERDETEKSI oleh ctranslate2 (count=0) — Whisper akan jalan "
            "di CPU. Cek libcudnn/libcublas di LD_LIBRARY_PATH."
        )


def main() -> int:
    _setup_logging()
    _log_runtime()

    from app.services.pipeline import run_video_pipeline

    task_id = UUID(os.environ["CLIPZI_TASK_ID"])
    result = asyncio.run(run_video_pipeline(task_id))
    print("PIPELINE_RESULT", result, flush=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
