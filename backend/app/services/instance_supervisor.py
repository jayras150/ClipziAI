"""
Supervisor instance Vast.ai — memantau instance dan mengganti otomatis bila gagal.

Vast.ai **tidak menyediakan webhook** (tidak ada di dokumentasi resmi), jadi
sinyal tercepat yang bisa dipakai ada dua:

1. **Polling** `show_instance()` tiap `VAST_SUPERVISOR_INTERVAL` detik (default 5)
   untuk melihat `actual_status`, `cur_state`, dan `status_msg`.
2. **Callback worker → API** (`POST /api/internal/worker/events`) yang dikirim
   container saat boot/progress/done/error — mendeteksi "instance running tapi
   onstart mati" dalam hitungan detik.

Kebijakan (agresif, sesuai keputusan produk):
  * maksimal `VAST_MAX_ATTEMPTS` (5) percobaan,
  * backoff `VAST_RETRY_BACKOFF` detik,
  * harga offer boleh naik sampai `VAST_MAX_PRICE_MULTIPLIER` (2×) dari offer
    pertama supaya task tetap berhasil,
  * instance lama SELALU dihapus dulu (tunggu hilang) sebelum membuat yang baru,
  * mesin (`machine_id`) yang gagal diblokir untuk sisa task ini.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Status yang menandakan instance tidak akan pernah menyelesaikan task.
FAILED_STATUSES = {"exited", "unknown", "error", "failed", "stopped", "offline"}
# Pola pesan error dari Vast (status_msg) yang berarti instance rusak.
FAILED_PATTERNS = re.compile(
    r"error|failed|no space|permission denied|pull access|manifest unknown|"
    r"not found|oom|out of memory|cannot|unable",
    re.IGNORECASE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InstanceSupervisor:
    """Pantau satu instance; ganti dengan offer baru kalau gagal."""

    def __init__(
        self,
        client: Any,
        task_id: Any,
        offer: Dict[str, Any],
        pick_offer: Callable[..., Awaitable[Dict[str, Any]]],
        create_instance: Callable[..., Awaitable[int]],
    ) -> None:
        self.client = client
        self.task_id = task_id
        self.offer = offer
        self.pick_offer = pick_offer
        self.create_instance = create_instance
        self.price_ceiling = float(offer.get("dph_total") or 0) * max(
            1.0, settings.VAST_MAX_PRICE_MULTIPLIER
        )
        self.exclude_machines: Set[int] = set()
        self.adopt_instance_id: Optional[int] = None

    # ---------------- database ----------------
    async def _record_create(
        self, instance_id: int, offer: Dict[str, Any], attempt: int, price: float
    ) -> Any:
        from app.db.session import AsyncSessionLocal
        from app.models.worker_instance import WorkerInstance

        try:
            async with AsyncSessionLocal() as db:
                row = WorkerInstance(
                    task_id=self.task_id,
                    instance_id=instance_id,
                    offer_id=offer.get("id"),
                    machine_id=offer.get("machine_id"),
                    gpu_name=str(offer.get("gpu_name") or "")[:80] or None,
                    price_per_hour=round(price, 4),
                    attempt=attempt,
                    state="creating",
                )
                db.add(row)
                await db.commit()
                await db.refresh(row)
                return row.id
        except Exception:
            # Observability tidak boleh menghentikan supervisor (kalau berhenti,
            # instance GPU bisa tertinggal hidup dan terus ditagih).
            logger.exception("Gagal mencatat worker_instances untuk instance %s", instance_id)
            return None

    async def _update_record(self, record_id: Any, **fields: Any) -> None:
        from app.db.session import AsyncSessionLocal
        from app.models.worker_instance import WorkerInstance

        if record_id is None:
            return
        try:
            async with AsyncSessionLocal() as db:
                row = await db.get(WorkerInstance, record_id)
                if row is None:
                    return
                for key, value in fields.items():
                    setattr(row, key, value)
                await db.commit()
        except Exception as exc:  # observability tidak boleh menghentikan task
            logger.warning("Gagal memperbarui worker_instances: %s", exc)

    async def _task_status(self) -> Optional[str]:
        from app.db.session import AsyncSessionLocal
        from app.models.task import Task

        async with AsyncSessionLocal() as db:
            task = await db.get(Task, self.task_id)
            return task.status.value if task and task.status else None

    async def _fail_task(self, message: str) -> None:
        from app.db.session import AsyncSessionLocal
        from app.models.task import Task, TaskStatus

        async with AsyncSessionLocal() as db:
            task = await db.get(Task, self.task_id)
            if task is None or task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.ERROR,
                TaskStatus.CANCELLED,
            }:
                return
            task.status = TaskStatus.ERROR
            task.error_message = message[:2000]
            await db.commit()
        logger.error("Task %s ditandai ERROR: %s", self.task_id, message)


    # ---------------- monitoring ----------------
    async def _watch(self, instance_id: int) -> tuple[str, str]:
        """Pantau satu instance. Return (outcome, reason): done|failed."""
        loop = asyncio.get_event_loop()
        started = time.monotonic()
        ready_at: Optional[float] = None
        last_msg = ""

        while True:
            status = await self._task_status()
            if status in {"completed", "error", "cancelled"}:
                return "done", status or "terminal"

            if time.monotonic() - started > settings.VAST_ONESHOT_TIMEOUT:
                return "failed", "melewati batas waktu task"

            try:
                info = await loop.run_in_executor(
                    None, self.client.show_instance, instance_id
                )
            except Exception as exc:
                logger.warning("show_instance(%s) gagal: %s", instance_id, exc)
                info = None

            if not info:
                return "failed", "instance hilang (404)"

            actual = str(info.get("actual_status") or "").lower()
            cur_state = str(info.get("cur_state") or "").lower()
            status_msg = str(info.get("status_msg") or "")
            if status_msg and status_msg != last_msg:
                last_msg = status_msg
                await self._update_record_by_instance(
                    instance_id, status_msg=status_msg[:1000]
                )

            if actual in FAILED_STATUSES or cur_state in {"exited", "stopped"}:
                return "failed", f"status={actual or cur_state}: {status_msg[:160]}"
            if (
                status_msg
                and FAILED_PATTERNS.search(status_msg)
                and "success" not in status_msg.lower()
            ):
                return "failed", f"status_msg: {status_msg[:160]}"

            if actual == "running":
                if ready_at is None:
                    ready_at = time.monotonic()
                    await self._update_record_by_instance(
                        instance_id, state="running", ready_at=_utcnow()
                    )
                    logger.info(
                        "Instance %s siap (running) untuk task %s",
                        instance_id,
                        self.task_id,
                    )
                elif time.monotonic() - ready_at > settings.VAST_WORKER_START_TIMEOUT:
                    # Instance hidup tapi worker tidak pernah memproses task.
                    if await self._task_status() == "queued":
                        return "failed", "onstart tidak pernah memproses task"
            elif ready_at is None and time.monotonic() - started > settings.VAST_BOOT_TIMEOUT:
                return "failed", f"boot timeout (status={actual or 'unknown'})"

            await asyncio.sleep(settings.VAST_SUPERVISOR_INTERVAL)

    async def _update_record_by_instance(self, instance_id: int, **fields: Any) -> None:
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.worker_instance import WorkerInstance

        try:
            async with AsyncSessionLocal() as db:
                row = (
                    await db.execute(
                        select(WorkerInstance)
                        .where(
                            WorkerInstance.task_id == self.task_id,
                            WorkerInstance.instance_id == instance_id,
                        )
                        .order_by(WorkerInstance.created_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if row is None:
                    return
                for key, value in fields.items():
                    setattr(row, key, value)
                await db.commit()
        except Exception as exc:
            logger.warning("Gagal memperbarui status instance %s: %s", instance_id, exc)


    # ---------------- lifecycle ----------------
    async def _destroy(self, instance_id: int, record_id: Any, reason: str) -> None:
        """Hapus instance lalu tunggu benar-benar hilang (biar tidak dobel tagih)."""
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self.client.destroy_instance, instance_id)
        except Exception as exc:
            logger.error("Gagal menghapus instance %s: %s", instance_id, exc)

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                info = await loop.run_in_executor(
                    None, self.client.show_instance, instance_id
                )
            except Exception:
                info = None
            if not info:
                break
            await asyncio.sleep(3)

        await self._update_record(
            record_id,
            state="destroyed",
            destroyed_at=_utcnow(),
            destroy_reason=reason[:120],
        )
        logger.info("Instance %s dihapus (task %s): %s", instance_id, self.task_id, reason)

    async def _collect_logs(self, instance_id: int) -> str:
        """Ambil potongan log instance (maks 20 s — jangan sampai supervisor macet)."""
        loop = asyncio.get_event_loop()
        try:
            text = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: self.client.logs(instance_id, tail="200")
                ),
                timeout=20,
            )
            return str(text)[-4000:]
        except Exception as exc:
            logger.warning("Gagal mengambil log instance %s: %s", instance_id, exc)
            return ""

    async def _next_offer(self) -> Dict[str, Any]:
        return await self.pick_offer(
            self.client,
            exclude_machines=self.exclude_machines,
            price_ceiling=self.price_ceiling,
        )

    async def run(self) -> Dict[str, Any]:
        """Jalankan sampai task selesai atau semua percobaan habis."""
        attempts = max(1, int(settings.VAST_MAX_ATTEMPTS))
        last_reason = "tidak diketahui"
        active_instance: Optional[int] = None

        try:
            for attempt in range(1, attempts + 1):
                try:
                    if self.adopt_instance_id is not None and attempt == 1:
                        # Lanjutkan instance yang sudah dibuat sebelum API restart.
                        instance_id = int(self.adopt_instance_id)
                        logger.warning(
                            "Task %s: mengadopsi instance %s yang masih hidup",
                            self.task_id,
                            instance_id,
                        )
                    else:
                        instance_id = int(await self.create_instance(self.offer))
                except Exception as exc:
                    last_reason = f"create_instance gagal: {str(exc)[:200]}"
                    logger.error("Percobaan %s: %s", attempt, last_reason)
                    if attempt >= attempts:
                        break
                    await asyncio.sleep(settings.VAST_RETRY_BACKOFF)
                    try:
                        self.offer = await self._next_offer()
                    except Exception as offer_exc:
                        last_reason = f"tidak ada offer pengganti: {offer_exc}"
                        break
                    continue

                active_instance = instance_id
                record_id = await self._record_create(
                    instance_id, self.offer, attempt, float(self.offer.get("dph_total") or 0)
                )
                logger.info(
                    "Task %s percobaan %s/%s: instance %s di %s ($%s/jam)",
                    self.task_id,
                    attempt,
                    attempts,
                    instance_id,
                    self.offer.get("gpu_name"),
                    self.offer.get("dph_total"),
                )

                outcome, reason = await self._watch(instance_id)
                if outcome == "done":
                    # Beri waktu singkat agar worker menyelesaikan unggahan log
                    # (qurl.sh) sebelum instance dimatikan.
                    await asyncio.sleep(10)
                    await self._destroy(instance_id, record_id, "task selesai")
                    active_instance = None
                    return {"ok": True, "instance_id": instance_id, "attempts": attempt}

                logger.warning(
                    "Instance %s gagal (percobaan %s): %s", instance_id, attempt, reason
                )
                last_reason = reason
                log_tail = await self._collect_logs(instance_id)
                await self._update_record(
                    record_id,
                    state="failed",
                    status_msg=reason[:1000],
                    log_tail=log_tail or None,
                )
                await self._destroy(
                    instance_id, record_id, f"attempt {attempt}: {reason}"
                )
                active_instance = None

                machine = self.offer.get("machine_id")
                if machine is not None:
                    try:
                        self.exclude_machines.add(int(machine))
                    except (TypeError, ValueError):
                        pass

                if attempt >= attempts:
                    break
                await asyncio.sleep(settings.VAST_RETRY_BACKOFF)
                try:
                    self.offer = await self._next_offer()
                except Exception as offer_exc:
                    last_reason = f"tidak ada offer pengganti: {str(offer_exc)[:160]}"
                    logger.error("%s", last_reason)
                    break
        finally:
            # Jaring pengaman: kalau supervisor berhenti karena exception, instance
            # yang masih hidup WAJIB dihapus supaya GPU tidak terus ditagih.
            if active_instance is not None:
                try:
                    logger.error(
                        "Supervisor berhenti tak terduga; menghapus instance %s",
                        active_instance,
                    )
                    await self._destroy(active_instance, None, "supervisor berhenti")
                except Exception:
                    logger.exception("Gagal menghapus instance %s", active_instance)

        await self._fail_task(
            "Worker GPU gagal dijalankan setelah beberapa percobaan: " + last_reason
        )
        return {"ok": False, "error": last_reason}
