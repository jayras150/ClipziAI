"""
Log worker GPU: penyimpanan + pembacaan untuk audit admin.

Dipanggil supervisor saat instance gagal (log container disalin sebelum
instance dihapus) dan oleh API admin untuk daftar/detail/hapus semua log.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_log import WorkerLog

logger = logging.getLogger(__name__)

MAX_LOG_BYTES = 200_000
FAILED_STATES = {"failed", "error", "timeout", "exited", "cancelled"}


def outcome_from(state: str | None, destroy_reason: str | None = None) -> str:
    """Tentukan hasil akhir worker: success | failed | cancelled | running."""
    text_state = str(state or "").lower()
    reason = str(destroy_reason or "").lower()
    if text_state in {"failed", "error", "timeout"}:
        return "failed"
    if text_state in {"exited", "cancelled"}:
        return "cancelled"
    if text_state == "destroyed":
        if "task selesai" in reason:
            return "success"
        if "batal" in reason or "cancelled" in reason:
            return "cancelled"
        if reason:
            return "failed"
        return "success"
    if text_state == "running" or text_state == "ready":
        return "running"
    return "running"


def _clip(text: str | None) -> Optional[str]:
    if not text:
        return None
    payload = str(text)
    if len(payload.encode("utf-8", errors="ignore")) <= MAX_LOG_BYTES:
        return payload
    return payload[-MAX_LOG_BYTES:]


def serialize(row: WorkerLog, with_log: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(row.id),
        "worker_instance_id": str(row.worker_instance_id) if row.worker_instance_id else None,
        "task_id": str(row.task_id) if row.task_id else None,
        "instance_id": row.instance_id,
        "outcome": row.outcome,
        "state": row.state,
        "reason": row.reason,
        "gpu_name": row.gpu_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "size": len((row.log_text or "").encode("utf-8", errors="ignore")),
    }
    if with_log:
        payload["log_text"] = row.log_text or ""
    return payload


async def record_failure(
    db: AsyncSession,
    *,
    worker_record_id: Any = None,
    task_id: Any = None,
    instance_id: Optional[int] = None,
    state: str = "failed",
    reason: str | None = None,
    log_text: str | None = None,
    gpu_name: str | None = None,
    outcome: str = "failed",
) -> Optional[str]:
    """Simpan log kegagalan worker (idempoten per instance+reason)."""
    try:
        if instance_id is not None:
            existing = (
                await db.execute(
                    select(WorkerLog.id)
                    .where(
                        WorkerLog.instance_id == instance_id,
                        WorkerLog.outcome == outcome,
                        WorkerLog.reason == (reason or None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing:
                return str(existing)
        row = WorkerLog(
            worker_instance_id=worker_record_id,
            task_id=task_id,
            instance_id=instance_id,
            outcome=outcome,
            state=str(state or "")[:24] or None,
            reason=(reason or None),
            gpu_name=(gpu_name or None),
            log_text=_clip(log_text),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return str(row.id)
    except Exception as exc:  # noqa: BLE001 - audit tidak boleh menghentikan supervisor
        logger.warning("Gagal menyimpan worker_log: %s", exc)
        await db.rollback()
        return None


async def list_logs(
    db: AsyncSession,
    *,
    outcome: str | None = None,
    q: str | None = None,
    limit: int = 50,
) -> Dict[str, Any]:
    query = select(WorkerLog).order_by(WorkerLog.created_at.desc()).limit(max(1, min(200, limit)))
    if outcome and outcome != "all":
        query = query.where(WorkerLog.outcome == outcome)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                WorkerLog.reason.ilike(like),
                WorkerLog.log_text.ilike(like),
                WorkerLog.gpu_name.ilike(like),
            )
        )
    rows = (await db.execute(query)).scalars().all()
    total = (await db.execute(select(func.count(WorkerLog.id)))).scalar() or 0
    return {"items": [serialize(row) for row in rows], "count": len(rows), "total": int(total)}


async def get_log(db: AsyncSession, log_id: UUID) -> Optional[Dict[str, Any]]:
    row = await db.get(WorkerLog, log_id)
    return serialize(row, with_log=True) if row else None


async def latest_for_task(db: AsyncSession, task_id: UUID) -> Optional[WorkerLog]:
    return (
        await db.execute(
            select(WorkerLog)
            .where(WorkerLog.task_id == task_id)
            .order_by(WorkerLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def clear_all(db: AsyncSession) -> Dict[str, Any]:
    total = (await db.execute(select(func.count(WorkerLog.id)))).scalar() or 0
    await db.execute(delete(WorkerLog))
    await db.commit()
    return {"ok": True, "deleted": int(total)}


__all__ = [
    "clear_all",
    "get_log",
    "latest_for_task",
    "list_logs",
    "outcome_from",
    "record_failure",
    "serialize",
]
