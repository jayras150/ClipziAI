"""
Vast Deployments (SDK ``@remote``) — alternatif dari worker HTTP.

Dua cara menjalankan worker GPU Clipzi:

1. **Worker HTTP** (default, sudah diverifikasi): ``deployments/worker_api.py``
   dijalankan di image yang sama dengan ``CLIPZI_ROLE=worker``; API mengirim job
   lewat ``POST {VAST_ENDPOINT_URL}/process``.

2. **Vast Deployments** (file ini): SDK mem-package & meng-upload kode, membuat
   endpoint + workergroup, lalu memanggil fungsi Python ``@remote`` langsung.

   ```bash
   pip install vastai
   export VAST_API_KEY=...            # atau isi backend/.env
   python -m deployments.app          # siapkan/selaraskan deployment
   ```

Catatan: seluruh pemakaian API di file ini sudah diverifikasi terhadap SDK
``vastai`` yang sebenarnya (``Deployment.remote``, ``.context``, ``.image``,
``.configure_autoscaling``, ``.async_ensure_ready``).

Semua definisi dibuat di dalam ``build_deployment()`` agar modul ini tetap bisa
di-import walau paket ``vastai`` belum terpasang (mis. di image API biasa).
"""
import asyncio
import logging
from typing import Any, Dict, Tuple

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def build_deployment() -> Tuple[Any, Any]:
    """Bangun objek Deployment + fungsi remote.

    Return ``(deployment, process_video_task)``.
    """
    try:
        from vastai import Deployment
    except ImportError as exc:  # pragma: no cover - opsional
        raise RuntimeError(
            "Paket `vastai` belum terpasang. Jalankan: pip install vastai"
        ) from exc

    deployment = Deployment(
        api_key=settings.VAST_API_KEY,
        name=settings.VAST_ENDPOINT_NAME,
    )

    # Image worker: image Clipzi sendiri (sudah berisi ffmpeg, yt-dlp, deps).
    # Kolom kedua = storage GB.
    image = deployment.image(
        settings.VAST_WORKER_IMAGE or "python:3.11-slim",
        int(settings.VAST_WORKER_DISK or 40),
    )
    image.apt_get("ffmpeg")
    image.env(
        CLIPZI_ROLE="worker",
        DEBUG="false",
    )
    # Base image polos: instal dependency aplikasi di dalam worker.
    if not settings.VAST_WORKER_IMAGE:
        image.pip_install("-r", "requirements.txt")

    deployment.configure_autoscaling(
        max_workers=settings.VAST_MAX_WORKERS,
        target_util=settings.VAST_TARGET_UTIL,
        inactivity_timeout=settings.VAST_INACTIVITY_TIMEOUT,
    )

    @deployment.remote()
    async def process_video_task(task_id: str) -> Dict[str, Any]:
        """Entry point remote: jalankan pipeline untuk satu task."""
        from uuid import UUID

        from app.services.pipeline import run_video_pipeline

        return await run_video_pipeline(UUID(task_id))

    return deployment, process_video_task


async def _main() -> None:
    deployment, _process_video_task = build_deployment()
    logger.info("Menyiapkan deployment '%s' di Vast.ai...", deployment.name)
    await deployment.async_ensure_ready()
    logger.info(
        "Deployment '%s' siap. Endpoint/workergroup dikelola otomatis oleh Vast.",
        deployment.name,
    )


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_main())
