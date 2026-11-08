"""
Dispatcher job dari API ke worker GPU (Vast.ai Serverless).

Tiga mode, dipilih otomatis dari konfigurasi:

  1. ``http``   — ``VAST_ENDPOINT_URL`` diisi.
                  POST {url}/process {"task_id": "..."} (paling portabel; jalan
                  untuk endpoint Vast maupun uvicorn lokal).
  2. ``sdk``    — ``VAST_API_KEY`` + ``VAST_ENDPOINT_NAME`` diisi.
                  Memakai SDK resmi: ``Serverless.queue_endpoint_request``.
                  Paket `vastai` harus terpasang di sisi API.
  3. ``inline`` — tidak ada konfigurasi Vast.
                  Pipeline dijalankan langsung di proses API (khusus development
                  tanpa GPU worker).

Mode tidak pernah memblokir respons HTTP ke user: request ke Vast dikirim
sebagai tugas background, sedangkan frontend memantau progres lewat polling
``GET /api/tasks/{id}``.
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_sdk_client: Optional[Any] = None


def dispatch_mode() -> str:
    """Tentukan mode dispatch yang aktif."""
    if (settings.VAST_ENDPOINT_URL or "").strip():
        return "http"
    if (settings.VAST_API_KEY or "").strip() and (settings.VAST_ENDPOINT_NAME or "").strip():
        return "sdk"
    return "inline"


async def _dispatch_http(task_id: UUID) -> Dict[str, Any]:
    """Kirim job ke worker lewat HTTP (fire-and-forget)."""
    import httpx

    endpoint_url = (settings.VAST_ENDPOINT_URL or "").strip().rstrip("/")
    url = endpoint_url + "/process"
    payload = {"task_id": str(task_id)}

    async def _post() -> None:
        try:
            async with httpx.AsyncClient(timeout=settings.VAST_REQUEST_TIMEOUT) as client:
                response = await client.post(url, json=payload)
            logger.info(
                "Worker HTTP menerima task %s (HTTP %s): %s",
                task_id,
                response.status_code,
                response.text[:200],
            )
        except Exception as exc:  # pragma: no cover - tergantung jaringan
            logger.error("Gagal mengirim task %s ke %s: %s", task_id, url, exc)

    asyncio.create_task(_post())
    return {"mode": "http", "endpoint": url, "queued": True}


def _get_sdk_client():
    """Buat (sekali) client Serverless SDK."""
    global _sdk_client
    if _sdk_client is None:
        try:
            from vastai import Serverless
        except ImportError as exc:  # pragma: no cover - opsional
            raise RuntimeError(
                "Mode SDK butuh paket `vastai`. Jalankan `pip install vastai`, "
                "atau isi VAST_ENDPOINT_URL untuk memakai mode HTTP."
            ) from exc
        _sdk_client = Serverless(api_key=settings.VAST_API_KEY)
    return _sdk_client


async def _dispatch_sdk(task_id: UUID) -> Dict[str, Any]:
    """Kirim job lewat SDK Vast (endpoint + workergroup yang dikelola)."""
    client = _get_sdk_client()
    endpoint = await client.get_endpoint(name=settings.VAST_ENDPOINT_NAME)

    request = client.queue_endpoint_request(
        endpoint=endpoint,
        worker_route="/process",
        worker_payload={"task_id": str(task_id)},
        cost=100,
        timeout=settings.VAST_REQUEST_TIMEOUT,
        worker_timeout=settings.VAST_REQUEST_TIMEOUT,
        retry=True,
    )

    def _on_done(result: Any) -> None:
        logger.info("Vast selesai memproses task %s: %s", task_id, str(result)[:300])

    try:
        request.then(_on_done)
    except Exception:  # pragma: no cover - API SDK bisa berubah
        logger.debug("ServerlessRequest.then() tidak tersedia; hasil tidak dilacak")

    return {
        "mode": "sdk",
        "endpoint": settings.VAST_ENDPOINT_NAME,
        "queued": True,
    }


async def _dispatch_inline(task_id: UUID) -> Dict[str, Any]:
    """Jalankan pipeline di proses API (development tanpa worker)."""
    from app.services.pipeline import run_video_pipeline

    asyncio.create_task(run_video_pipeline(task_id))
    return {"mode": "inline", "queued": True}


async def submit_task(task_id: UUID) -> Dict[str, Any]:
    """Kirim satu task ke worker sesuai mode yang aktif.

    Tidak pernah melempar exception: kegagalan dispatch dicatat di log dan
    dikembalikan sebagai dict berisi ``error`` supaya task tetap tersimpan dan
    bisa di-retry manual.
    """
    mode = dispatch_mode()
    try:
        if mode == "http":
            result = await _dispatch_http(task_id)
        elif mode == "sdk":
            result = await _dispatch_sdk(task_id)
        else:
            result = await _dispatch_inline(task_id)
        logger.info("Task %s didispatch via %s", task_id, mode)
        return result
    except Exception as exc:
        logger.error("Dispatch task %s (%s) gagal: %s", task_id, mode, exc)
        return {"mode": mode, "queued": False, "error": str(exc)}
