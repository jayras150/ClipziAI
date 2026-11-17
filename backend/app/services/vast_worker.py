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
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

import requests

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.services.instance_supervisor import InstanceSupervisor

logger = logging.getLogger(__name__)

settings = get_settings()

_sdk_client: Optional[Any] = None
_vast_client: Optional[Any] = None


def _gpu_key(name: Any) -> str:
    """Normalisasi nama GPU untuk pencocokan allowlist ('RTX 4090' == 'RTX_4090')."""
    import re

    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


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
    # Allowlist GPU (opsional) difilter di sini agar tidak bergantung sintaks query.
    from app.services.vast_config import normalize_allowlist

    allowlist = normalize_allowlist(settings.VAST_GPU_ALLOWLIST)
    if allowlist:
        allowed = {_gpu_key(name) for name in allowlist}
        usable = [offer for offer in usable if _gpu_key(offer.get("gpu_name")) in allowed]
        if not usable:
            raise RuntimeError(
                "tidak ada offer GPU yang diizinkan "
                f"({', '.join(allowlist)}); filter: {query}"
            )
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

            # Task yang sudah dihapus user tidak akan pernah menjadi terminal;
            # tanpa cek None reaper menunggu timeout penuh (GPU tetap ditagih).
            if status is None or status in terminal:
                reason = status.value if status else "task dihapus"
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
    try:
        await supervisor.run()
    except Exception:
        logger.exception("Supervisor instance gagal untuk task %s", supervisor.task_id)


WORKER_ENV_REQUIRED = (
    "CLIPZI_CALLBACK_URL",
    "CLIPZI_WORKER_TOKEN",
    "DATABASE_URL",
    "ENCRYPTION_KEY",
    "SECRET_KEY",
)

WORKER_ENV_OPTIONAL = (
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "REDIS_URL",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_DOMAIN",
    "YTDLP_PROXY",
    "YTDLP_COOKIES_BASE64",
    "YTDLP_EXTRACTOR_ARGS",
    "HF_TOKEN",
)


WORKER_ENV_MAX_CHARS = 3600
WORKER_ENV_HARD_LIMIT = 3900


def _pack_worker_env(env: Dict[str, str]) -> Dict[str, str]:
    """Jaga total env di bawah batas Vast (~4 KB).

    Cookies YouTube (base64) biasanya > 4 KB sehingga seluruh request create
    instance ditolak `400 invalid_args` (pesannya menyesatkan: "invalid template
    hash"). Kalau total env terlalu besar, cookies dikirim dalam bentuk
    gzip+base64 (jauh lebih kecil) dan worker meng-expand saat start.
    """
    cookies = env.get("YTDLP_COOKIES_BASE64")
    if not cookies:
        return env
    total = sum(len(str(key)) + len(str(value)) for key, value in env.items())
    if total <= WORKER_ENV_MAX_CHARS:
        return env
    try:
        import base64
        import gzip

        # Kompres ISI cookies (bukan string base64-nya) supaya hasilnya jauh
        # lebih kecil; worker melakukan kebalikannya.
        raw = base64.b64decode(cookies.encode("ascii"), validate=False)
        packed = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal mengompres cookies worker: %s", exc)
        return env
    if len(packed) < len(cookies):
        env.pop("YTDLP_COOKIES_BASE64", None)
        env["YTDLP_COOKIES_GZIP_B64"] = packed
        logger.info(
            "Env worker dipadatkan: cookies %s -> %s karakter (total ~%s)",
            len(cookies),
            len(packed),
            sum(len(str(key)) + len(str(value)) for key, value in env.items()),
        )
    # Batas keras Vast ±4096 karakter untuk seluruh env.
    total = sum(len(str(key)) + len(str(value)) for key, value in env.items())
    if total > WORKER_ENV_HARD_LIMIT:
        env.pop("YTDLP_COOKIES_GZIP_B64", None)
        env.pop("YTDLP_COOKIES_BASE64", None)
        env["YTDLP_COOKIES_MISSING"] = "1"
        logger.warning(
            "Env worker tetap %s karakter setelah dipadatkan; cookies dihapus agar "
            "instance tetap bisa dibuat",
            total,
        )
    return env


def build_worker_env(task_id: Optional[UUID] = None) -> Dict[str, str]:
    """Env yang dibutuhkan instance worker — SATU sumber untuk dispatch & export admin."""
    env: Dict[str, str] = {"CLIPZI_ROLE": "worker"}
    if task_id is not None:
        env["CLIPZI_TASK_ID"] = str(task_id)
    for name in WORKER_ENV_REQUIRED + WORKER_ENV_OPTIONAL:
        value = getattr(settings, name, None)
        if value:
            env[name] = str(value)
    if getattr(settings, "VAST_MODEL_BAKED", False):
        # Model sudah ada di image: jangan kirim URL/restore env apa pun.
        env["CLIPZI_MODEL_SOURCE"] = "baked"
        env["GPU_WHISPER_MODEL"] = "/app/whisper_model"
        return _pack_worker_env(env)
    return _pack_worker_env(env)


def _vast_error_text(exc: Exception, limit: int = 700) -> str:
    """Ambil pesan asli Vast (body JSON), bukan cuma "400 Client Error for url"."""
    response = getattr(exc, "response", None)
    if response is None:
        return str(exc)[:limit]
    body = ""
    try:
        body = response.text or ""
    except Exception:  # noqa: BLE001
        body = ""
    status = getattr(response, "status_code", "?")
    if body:
        return f"HTTP {status}: {body[:limit]}"
    return f"HTTP {status}: {str(exc)[:limit]}"


def _ask_missing(offer_id: Any) -> bool:
    """Cek cepat apakah ask Vast masih ada (ask kerap diambil mesin lain)."""
    key = (settings.VAST_API_KEY or "").strip()
    if not key or offer_id is None:
        return False
    try:
        response = requests.get(
            f"https://console.vast.ai/api/v0/asks/{offer_id}/",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=10,
        )
    except Exception:  # noqa: BLE001 - gagal cek ≠ gagal dispatch
        return False
    return response.status_code == 404


def _stale_offer_error(text: str) -> bool:
    """Error yang berarti 'offer sudah tidak tersedia' (bukan payload salah)."""
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "ask",
            "no longer",
            "not found",
            "unavailable",
            "gone",
            "could not be found",
            "resource could not be found",
        )
    )


def _post_create_instance(
    offer_id: Any,
    *,
    disk: float,
    env: Dict[str, Any],
    label: str,
    onstart: str,
    image: str = "",
    template_hash: str = "",
) -> Dict[str, Any]:
    """POST create-instance langsung ke Vast tanpa field yang tidak dipakai.

    SDK `vastai` selalu mengirim `"template_hash_id": null` saat hanya memakai
    image; Vast membalas `400 invalid_args: invalid template hash or id or
    template not accessible by user`. Jadi payload dibangun sendiri: field
    template hanya dikirim kalau memang ada.
    """
    key = (settings.VAST_API_KEY or "").strip()
    if not key:
        raise RuntimeError("VAST_API_KEY belum diset")
    payload: Dict[str, Any] = {
        "client_id": "me",
        "disk": float(disk),
        "env": env,
        "label": label,
        "onstart": onstart,
        "cancel_unavail": True,
    }
    if template_hash:
        payload["template_hash_id"] = template_hash
    else:
        payload["image"] = image
    response = requests.put(
        f"https://console.vast.ai/api/v0/asks/{offer_id}/",
        json=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=90,
    )
    if not response.ok:
        body = (response.text or "").strip()
        error = requests.HTTPError(
            f"{response.status_code} Client Error for url: {response.url}", response=response
        )
        raise error
    try:
        return response.json() or {}
    except ValueError as exc:
        raise RuntimeError(f"Respons Vast tidak valid: {(response.text or '')[:200]}") from exc


def _make_create_instance(task_id: UUID, client: Any):
    """Factory pembuat instance (dipakai dispatch DAN resume setelah restart).

    Sebelumnya `resume_supervisors()` mengirim `create_instance=None`, sehingga
    saat instance hasil adopsi gagal dan supervisor mencoba percobaan ke-2,
    muncul `'NoneType' object is not callable` dan task langsung mati.
    """
    image = (settings.VAST_WORKER_IMAGE or "").strip()
    template_hash = (settings.VAST_TEMPLATE_HASH or "").strip()
    if not image and not template_hash:
        raise RuntimeError(
            "Mode oneshot butuh VAST_WORKER_IMAGE (atau VAST_TEMPLATE_HASH) di .env. "
            "Contoh: VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0"
        )

    async def _create(selected: Dict[str, Any]) -> int:
        offer_id = selected.get("id")
        if not offer_id:
            raise RuntimeError(f"offer tidak punya id: {selected}")
        worker_env = build_worker_env(task_id)

        # Ask Vast cepat hilang (diambil mesin lain). Kalau itu terjadi, ambil
        # offer baru dan coba lagi — jangan langsung menggagalkan task.
        # Template hash yang tersimpan bisa sudah tidak valid/terhapus; dalam
        # kasus itu dispatch jatuh ke mode image (kalau VAST_WORKER_IMAGE ada).
        last_error = ""
        current = selected
        use_template = bool(template_hash)
        for attempt in range(1, 4):
            current_id = current.get("id")
            if not current_id:
                raise RuntimeError(f"offer tidak punya id: {current}")
            try:
                created = await asyncio.to_thread(
                    _post_create_instance,
                    current_id,
                    disk=settings.VAST_WORKER_DISK,
                    env=worker_env,
                    label=f"clipzi-{str(task_id)[:8]}",
                    onstart=_oneshot_onstart(task_id),
                    image=image,
                    template_hash=template_hash if use_template else "",
                )
            except Exception as exc:  # noqa: BLE001 - klasifikasikan lalu retry
                text = _vast_error_text(exc)
                lowered = text.lower()
                if use_template and "template" in lowered and image:
                    logger.warning(
                        "Template Vast tidak valid (%s); beralih ke image %s",
                        text[:160],
                        image,
                    )
                    use_template = False
                    last_error = text
                    continue
                if _stale_offer_error(text):
                    note = " (ask sudah tidak tersedia di Vast)" if _ask_missing(current_id) else ""
                    last_error = f"{text}{note}"
                    logger.warning(
                        "Task %s: offer %s tidak bisa dipakai (coba %s/3): %s — memilih offer lain",
                        task_id,
                        current_id,
                        attempt,
                        last_error,
                    )
                    current = await _pick_offer(client)
                    continue
                logger.warning(
                    "Task %s: create_instance gagal (offer %s): %s",
                    task_id,
                    current_id,
                    text,
                )
                raise RuntimeError(f"create_instance gagal: {text}") from exc
            instance_id = created.get("new_contract") or created.get("instance_id")
            if not instance_id:
                raise RuntimeError(f"create_instance tidak mengembalikan instance id: {created}")
            instance_id = int(instance_id)
            return instance_id

        raise RuntimeError(
            f"create_instance gagal setelah 3 offer dicoba. Error terakhir: {last_error}"
        )

    return _create


async def _dispatch_oneshot(task_id: UUID) -> Dict[str, Any]:
    """Buat instance GPU untuk task ini, lalu pantau & ganti otomatis bila gagal."""
    client = _get_vast_client()
    create_instance = _make_create_instance(task_id, client)
    offer = await _pick_offer(client)
    logger.info(
        "Task %s: offer awal %s (%s $%s/jam)",
        task_id,
        offer.get("id"),
        offer.get("gpu_name"),
        offer.get("dph_total"),
    )

    from app.services.instance_supervisor import InstanceSupervisor

    supervisor = InstanceSupervisor(
        client=client,
        task_id=task_id,
        offer=offer,
        pick_offer=_pick_offer,
        create_instance=create_instance,
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


async def destroy_task_instances(task_id: UUID, reason: str = "task dihapus") -> Dict[str, Any]:
    """Hentikan semua instance GPU milik satu task (best effort).

    Dipanggil saat user menghapus task atau admin membatalkan task. Tanpa ini
    instance tetap hidup sampai reaper/timeout karena task sudah tidak ada.
    """
    from sqlalchemy import select

    from app.db.session import AsyncSessionLocal
    from app.models.worker_instance import WorkerInstance

    instance_ids: set[int] = set()
    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(WorkerInstance).where(WorkerInstance.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.instance_id and (row.state or "") != "destroyed":
                instance_ids.add(int(row.instance_id))

    if not instance_ids:
        return {"destroyed": 0, "errors": []}

    destroyed = 0
    errors: list[str] = []
    try:
        client = _get_vast_client()
    except Exception as exc:  # noqa: BLE001
        return {"destroyed": 0, "errors": [f"Vast client tidak siap: {exc}"]}

    for instance_id in sorted(instance_ids):
        try:
            await asyncio.to_thread(client.destroy_instance, instance_id)
            destroyed += 1
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "404" in message or "not found" in message.lower():
                destroyed += 1
            else:
                errors.append(f"{instance_id}: {message[:160]}")
                logger.warning("Gagal menghapus instance %s task %s: %s", instance_id, task_id, exc)

    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(WorkerInstance).where(WorkerInstance.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.instance_id and int(row.instance_id) in instance_ids:
                row.state = "destroyed"
                row.destroyed_at = datetime.utcnow()
                row.destroy_reason = reason[:120]
        await db.commit()

    return {"destroyed": destroyed, "errors": errors}


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
                    # WAJIB factory asli: kalau instance adopsi gagal, supervisor
                    # harus bisa membuat instance pengganti.
                    create_instance=_make_create_instance(row.task_id, client),
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
