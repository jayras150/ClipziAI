"""
Dispatcher job dari API ke worker GPU (Vast.ai).

Empat mode, dipilih dari konfigurasi:

  1. ``http``    — ``VAST_ENDPOINT_URL`` diisi.
                   POST {url}/process {"task_id": "..."} (paling portabel; jalan
                   untuk endpoint Vast maupun uvicorn lokal).
  2. ``sdk``     — ``VAST_API_KEY`` + ``VAST_ENDPOINT_NAME`` diisi.
                   Memakai SDK resmi: ``Serverless.queue_endpoint_request``.
                   Paket `vastai` harus terpasang di sisi API.
  3. ``oneshot`` — ``VAST_DISPATCH_MODE=oneshot``.
                   API membuat SATU instance GPU khusus task ini, worker
                   menjalankannya lewat onstart, lalu instance **dihapus** setelah
                   task selesai (reaper). GPU hanya hidup selama task berjalan.
  4. ``inline``  — tidak ada konfigurasi Vast.
                   Pipeline dijalankan langsung di proses API (khusus development
                   tanpa GPU worker).

Mode tidak pernah memblokir respons HTTP ke user: request ke Vast dikirim
sebagai tugas background, sedangkan frontend memantau progres lewat polling
``GET /api/tasks/{id}``.

Catatan mode ``oneshot``
------------------------
* Provisioning instance butuh ~2–5 menit, jadi mode ini cocok untuk task besar
  atau batch, bukan untuk SLA ketat.
* Secret (DATABASE_URL, R2_*, API key) TIDAK dikirim lewat argumen. Set sekali
  sebagai Environment Variables akun Vast::

      vastai create env-var DATABASE_URL "postgresql+asyncpg://..."

* Reaper selalu menghapus instance lewat ``finally`` — termasuk saat task error,
  worker gagal boot, atau melewati ``VAST_ONESHOT_TIMEOUT``.
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID


from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_sdk_client: Optional[Any] = None
_vast_client: Optional[Any] = None


def dispatch_mode() -> str:
    """Tentukan mode dispatch yang aktif."""
    forced = (settings.VAST_DISPATCH_MODE or "").strip().lower()
    if forced in {"http", "sdk", "oneshot", "inline"}:
        return forced
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


def _get_vast_client():
    """Buat (sekali) client `VastAI` untuk mengelola instance."""
    global _vast_client
    if _vast_client is None:
        try:
            from vastai import VastAI
        except ImportError as exc:  # pragma: no cover - opsional
            raise RuntimeError(
                "Mode oneshot butuh paket `vastai`. Jalankan `pip install vastai`."
            ) from exc
        _vast_client = VastAI(api_key=settings.VAST_API_KEY)
    return _vast_client


def _oneshot_onstart(task_id: UUID) -> str:
    """Perintah yang dijalankan di dalam container worker saat instance boot."""
    return (
        "cd /app && python -c "
        "'import asyncio; from uuid import UUID; "
        "from app.services.pipeline import run_video_pipeline; "
        f'r = asyncio.run(run_video_pipeline(UUID("{task_id}"))); '
        'print("PIPELINE_RESULT", r); '
        "raise SystemExit(0 if r.get(\"ok\") else 1)'"
    )


async def _pick_offer(client: Any) -> Dict[str, Any]:
    """Cari offer GPU termurah yang memenuhi filter & batas harga."""
    query = (settings.VAST_GPU_FILTER or "").strip()
    offers = await asyncio.to_thread(client.search_offers, query, "on-demand", "score-", 20)
    if not offers:
        raise RuntimeError(f"tidak ada offer GPU untuk filter: {query}")

    def _price(offer: Dict[str, Any]) -> float:
        return float(offer.get("dph_total") or 0)

    usable = [
        offer
        for offer in offers
        if offer.get("rentable")
        and _price(offer) > 0
        and (
            settings.VAST_ONESHOT_MAX_PRICE <= 0
            or _price(offer) <= settings.VAST_ONESHOT_MAX_PRICE
        )
    ]
    if not usable:
        raise RuntimeError(
            f"tidak ada offer di bawah ${settings.VAST_ONESHOT_MAX_PRICE}/jam "
            f"(filter: {query})"
        )
    usable.sort(key=_price)
    return usable[0]


async def _reap_instance(instance_id: int, task_id: UUID) -> None:
    """Hapus instance setelah task selesai / error / timeout.

    Instance selalu dihapus lewat ``finally`` sehingga GPU berhenti ditagih walau
    worker gagal boot, pipeline crash, atau API kehabisan waktu.
    """
    from app.db.session import AsyncSessionLocal
    from app.models.task import Task, TaskStatus

    client = _get_vast_client()
    terminal = {TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED}
    deadline = time.monotonic() + settings.VAST_ONESHOT_TIMEOUT
    boot_deadline = time.monotonic() + settings.VAST_ONESHOT_BOOT_TIMEOUT
    reason = "timeout"

    try:
        while time.monotonic() < deadline:
            await asyncio.sleep(settings.VAST_ONESHOT_REAP_INTERVAL)
            async with AsyncSessionLocal() as db:
                task = await db.get(Task, task_id)
                status = task.status if task else None

            if status in terminal:
                reason = status.value if status else "unknown"
                break

            if status == TaskStatus.QUEUED and time.monotonic() > boot_deadline:
                reason = "worker tidak pernah memproses task (boot timeout)"
                logger.error("Task %s: %s", task_id, reason)
                async with AsyncSessionLocal() as db:
                    task = await db.get(Task, task_id)
                    if task and task.status == TaskStatus.QUEUED:
                        task.status = TaskStatus.ERROR
                        task.error_message = (
                            "Worker GPU gagal memproses task (boot timeout). "
                            "Silakan jalankan ulang task."
                        )
                        await db.commit()
                break
        else:
            logger.error(
                "Task %s melewati %s detik; instance %s dihapus paksa",
                task_id,
                settings.VAST_ONESHOT_TIMEOUT,
                instance_id,
            )
    except asyncio.CancelledError:  # pragma: no cover - saat API dimatikan
        reason = "cancelled"
        raise
    except Exception as exc:  # pragma: no cover - DB/jaringan
        reason = f"reaper error: {exc}"
        logger.error("Reaper task %s gagal memantau: %s", task_id, exc)
    finally:
        try:
            await asyncio.to_thread(client.destroy_instance, instance_id)
            logger.info(
                "Instance %s dihapus (task %s: %s) — tagihan GPU berhenti",
                instance_id,
                task_id,
                reason,
            )
        except Exception as exc:  # pragma: no cover - jaringan
            logger.error(
                "GAGAL menghapus instance %s (task %s): %s — hapus manual: "
                "vastai destroy instance %s -y",
                instance_id,
                task_id,
                exc,
                instance_id,
            )


async def _dispatch_oneshot(task_id: UUID) -> Dict[str, Any]:
    """Buat satu instance GPU untuk task ini, lalu hapus otomatis setelah selesai."""
    image = (settings.VAST_WORKER_IMAGE or "").strip()
    template_hash = (settings.VAST_TEMPLATE_HASH or "").strip()
    if not image and not template_hash:
        raise RuntimeError(
            "Mode oneshot butuh VAST_WORKER_IMAGE (atau VAST_TEMPLATE_HASH) di .env. "
            "Contoh: VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0"
        )

    client = _get_vast_client()
    offer = await _pick_offer(client)
    logger.info(
        "Task %s: membuat instance one-shot pada offer %s (%s $%s/jam)",
        task_id,
        offer.get("id"),
        offer.get("gpu_name"),
        offer.get("dph_total"),
    )

    kwargs: Dict[str, Any] = {
        "disk": settings.VAST_WORKER_DISK,
        "env": {"CLIPZI_ROLE": "worker"},
        "label": f"clipzi-{str(task_id)[:8]}",
        "onstart_cmd": _oneshot_onstart(task_id),
        "cancel_unavail": True,
    }
    if template_hash:
        kwargs["template_hash"] = template_hash
    else:
        kwargs["image"] = image

    created = await asyncio.to_thread(client.create_instance, offer["id"], **kwargs)
    instance_id = created.get("new_contract") or created.get("instance_id")
    if not instance_id:
        raise RuntimeError(f"create_instance tidak mengembalikan instance id: {created}")

    # Reaper dipasang segera; respons ke user tidak menunggu instance siap.
    asyncio.create_task(_reap_instance(int(instance_id), task_id))

    return {
        "mode": "oneshot",
        "queued": True,
        "instance_id": instance_id,
        "offer_id": offer.get("id"),
        "price_per_hour": offer.get("dph_total"),
    }


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
        elif mode == "oneshot":
            result = await _dispatch_oneshot(task_id)
        else:
            result = await _dispatch_inline(task_id)
        logger.info("Task %s didispatch via %s", task_id, mode)
        return result
    except Exception as exc:
        logger.error("Dispatch task %s (%s) gagal: %s", task_id, mode, exc)
        return {"mode": mode, "queued": False, "error": str(exc)}
