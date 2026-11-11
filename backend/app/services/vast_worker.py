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
    """Path script onstart di dalam image (task id dikirim lewat env).

    Penting: Vast mengeksekusi `onstart` sebagai exec (tanpa shell), jadi
    perintah panjang seperti `cd /app && python -c '...'` GAGAL dengan
    "no such file or directory". Karena itu kita hanya mengirim path script
    (`/app/deployments/pipeline_onstart.sh`) dan task id lewat `CLIPZI_TASK_ID`.
    """
    return "/app/deployments/pipeline_onstart.sh"


async def _pick_offer(
    client: Any,
    exclude_machines: Optional[set] = None,
    price_ceiling: float = 0.0,
) -> Dict[str, Any]:
    """Cari offer GPU termurah yang memenuhi filter, harga, dan mesin.

    `exclude_machines` dipakai supervisor untuk menghindari mesin yang baru saja
    gagal boot. `price_ceiling` = batas harga percobaan berikutnya (boleh naik
    sampai `VAST_MAX_PRICE_MULTIPLIER` × harga offer pertama).
    """
    query = (settings.VAST_GPU_FILTER or "").strip()
    offers = await asyncio.to_thread(client.search_offers, query, "on-demand", "dph_total+", 100)
    if not offers:  # fallback: sebagian versi SDK memakai nama urutan lain
        offers = await asyncio.to_thread(client.search_offers, query, "on-demand", "score-", 100)
    if not offers:
        raise RuntimeError(f"tidak ada offer GPU untuk filter: {query}")

    def _price(offer: Dict[str, Any]) -> float:
        return float(offer.get("dph_total") or 0)

    caps = [value for value in (price_ceiling, settings.VAST_ONESHOT_MAX_PRICE) if value and value > 0]
    hard_cap = min(caps) if caps else 0.0
    blocked = {int(m) for m in (exclude_machines or set())}

    usable = [
        offer
        for offer in offers
        if offer.get("rentable")
        and _price(offer) > 0
        and (hard_cap <= 0 or _price(offer) <= hard_cap)
        and int(offer.get("machine_id") or 0) not in blocked
    ]
    if not usable:
        raise RuntimeError(
            f"tidak ada offer di bawah ${hard_cap or 'tanpa batas'}/jam "
            f"(filter: {query}, mesin diblokir: {sorted(blocked)})"
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


async def _supervise_safely(supervisor: "InstanceSupervisor") -> None:
    """Jalankan supervisor; exception apa pun dicatat, bukan hilang diam-diam."""
    from app.services.instance_supervisor import InstanceSupervisor  # noqa: F401

    try:
        await supervisor.run()
    except Exception:
        logger.exception("Supervisor instance gagal untuk task %s", supervisor.task_id)


async def _dispatch_oneshot(task_id: UUID) -> Dict[str, Any]:
    """Buat instance GPU untuk task ini, lalu pantau & ganti otomatis bila gagal."""
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
        "Task %s: offer awal %s (%s $%s/jam)",
        task_id,
        offer.get("id"),
        offer.get("gpu_name"),
        offer.get("dph_total"),
    )

    async def _create(selected: Dict[str, Any]) -> int:
        worker_env = {"CLIPZI_ROLE": "worker", "CLIPZI_TASK_ID": str(task_id)}
        if settings.CLIPZI_CALLBACK_URL:
            worker_env["CLIPZI_CALLBACK_URL"] = settings.CLIPZI_CALLBACK_URL
        if settings.CLIPZI_WORKER_TOKEN:
            worker_env["CLIPZI_WORKER_TOKEN"] = settings.CLIPZI_WORKER_TOKEN
        kwargs: Dict[str, Any] = {
            "disk": settings.VAST_WORKER_DISK,
            # CLIPZI_TASK_ID dibaca script onstart di dalam image.
            "env": worker_env,
            "label": f"clipzi-{str(task_id)[:8]}",
            "onstart_cmd": _oneshot_onstart(task_id),
            "cancel_unavail": True,
        }
        if template_hash:
            kwargs["template_hash"] = template_hash
        else:
            kwargs["image"] = image
        created = await asyncio.to_thread(
            client.create_instance, selected["id"], **kwargs
        )
        instance_id = created.get("new_contract") or created.get("instance_id")
        if not instance_id:
            raise RuntimeError(f"create_instance tidak mengembalikan instance id: {created}")
        return int(instance_id)

    from app.services.instance_supervisor import InstanceSupervisor

    supervisor = InstanceSupervisor(
        client=client,
        task_id=task_id,
        offer=offer,
        pick_offer=_pick_offer,
        create_instance=_create,
    )
    # Pantau + auto-replace di background; respons ke user tidak menunggu boot.
    asyncio.create_task(_supervise_safely(supervisor))

    return {
        "mode": "oneshot",
        "queued": True,
        "offer_id": offer.get("id"),
        "machine_id": offer.get("machine_id"),
        "price_per_hour": offer.get("dph_total"),
        "max_attempts": settings.VAST_MAX_ATTEMPTS,
    }


async def cleanup_orphan_instances() -> int:
    """Hapus instance berlabel ``clipzi-*`` yang task-nya sudah tidak aktif.

    Dipanggil saat API start. Menangani kasus API restart / crash sehingga reaper
    di memori hilang dan instance GPU tertinggal hidup (terus ditagih).
    Mengembalikan jumlah instance yang dihapus.
    """
    key = (settings.VAST_API_KEY or "").strip()
    if not key:
        return 0

    from sqlalchemy import String, cast, select

    from app.db.session import AsyncSessionLocal
    from app.models.task import Task, TaskStatus

    try:
        client = _get_vast_client()
        instances = await asyncio.to_thread(client.show_instances)
    except Exception as exc:  # pragma: no cover - jaringan/SDK
        logger.warning("Pemeriksaan instance yatim dilewati: %s", exc)
        return 0

    if not isinstance(instances, list):
        return 0

    active = {TaskStatus.QUEUED, TaskStatus.PROCESSING}
    removed = 0

    for instance in instances:
        label = str(instance.get("label") or "")
        if not label.startswith("clipzi-"):
            continue
        instance_id = instance.get("id") or instance.get("instance_id")
        if not instance_id:
            continue

        prefix = label[len("clipzi-"):].lower()
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Task.status).where(cast(Task.id, String).like(f"{prefix}%"))
            )
            statuses = [row[0] for row in result.all()]

        # Task masih dikerjakan -> biarkan reaper normal yang menghapus.
        if any(status in active for status in statuses):
            continue

        try:
            await asyncio.to_thread(client.destroy_instance, int(instance_id))
            removed += 1
            logger.warning(
                "Instance yatim %s (label %s) dihapus saat startup", instance_id, label
            )
        except Exception as exc:  # pragma: no cover - jaringan
            logger.error("Gagal menghapus instance yatim %s: %s", instance_id, exc)

    return removed


async def resume_supervisors() -> int:
    """Adopsi instance yang masih hidup setelah API restart.

    Tanpa ini, restart container API membuat supervisor hilang sementara instance
    GPU tetap jalan (dan terus ditagih) sampai task timeout. Dipanggil saat startup
    bersama `cleanup_orphan_instances()`.
    """
    key = (settings.VAST_API_KEY or "").strip()
    if not key or settings.VAST_DISPATCH_MODE not in {None, "", "oneshot"}:
        return 0

    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.task import Task, TaskStatus
    from app.models.worker_instance import WorkerInstance
    from app.services.instance_supervisor import InstanceSupervisor

    adopted = 0
    seen_tasks: set = set()
    try:
        client = _get_vast_client()
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(WorkerInstance)
                    .where(WorkerInstance.state.in_(["creating", "running", "worker_started"]))
                    .order_by(WorkerInstance.created_at.desc())
                )
            ).scalars().all()

            for row in rows:
                if row.task_id in seen_tasks or not row.instance_id:
                    continue
                seen_tasks.add(row.task_id)
                task = await db.get(Task, row.task_id)
                if task is None or task.status not in {
                    TaskStatus.QUEUED,
                    TaskStatus.PROCESSING,
                }:
                    continue

                supervisor = InstanceSupervisor(
                    client=client,
                    task_id=row.task_id,
                    offer={
                        "id": row.offer_id,
                        "machine_id": row.machine_id,
                        "gpu_name": row.gpu_name,
                        "dph_total": row.price_per_hour,
                    },
                    pick_offer=_pick_offer,
                    create_instance=None,  # type: ignore[arg-type]
                )
                supervisor.adopt_instance_id = int(row.instance_id)
                asyncio.create_task(_supervise_safely(supervisor))
                adopted += 1
                logger.warning(
                    "Startup: melanjutkan pemantauan instance %s untuk task %s",
                    row.instance_id,
                    row.task_id,
                )
    except Exception as exc:
        logger.warning("Resume supervisor dilewati: %s", exc)
    return adopted


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
            # Mode `inline` menjalankan pipeline di proses API — artinya render
            # ffmpeg + Whisper memakan CPU/RAM server hosting (VPS). Itu hanya
            # boleh untuk development (DEBUG=True). Di produksi task ditolak
            # dengan pesan jelas supaya beban berat tetap di worker GPU Vast.ai.
            if not settings.DEBUG:
                logger.error(
                    "Task %s ditolak: dispatch mode 'inline' tidak diizinkan di produksi",
                    task_id,
                )
                return {
                    "mode": "inline",
                    "queued": False,
                    "error": (
                        "Worker GPU belum terkonfigurasi. Pipeline tidak dijalankan di "
                        "server API — set VAST_DISPATCH_MODE=oneshot beserta VAST_API_KEY "
                        "dan VAST_WORKER_IMAGE agar pemrosesan berjalan di Vast.ai."
                    ),
                }
            result = await _dispatch_inline(task_id)
        logger.info("Task %s didispatch via %s", task_id, mode)
        return result
    except Exception as exc:
        logger.error("Dispatch task %s (%s) gagal: %s", task_id, mode, exc)
        return {"mode": mode, "queued": False, "error": str(exc)}
