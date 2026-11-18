"""
Admin: monitor instance GPU Vast.ai (riwayat + aksi hapus paksa).

Berguna saat worker gagal boot: admin bisa melihat mesin mana yang bermasalah,
berapa percobaan, harga, dan potongan log terakhir tanpa membuka dashboard Vast.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.core.config import get_settings
from app.models.user import User
from app.models.worker_instance import WorkerInstance
from app.models.worker_log import WorkerLog
from app.services import vast_admin, worker_logs

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(row: WorkerInstance, has_log: bool = False) -> Dict[str, Any]:
    return {
        "outcome": worker_logs.outcome_from(row.state, row.destroy_reason),
        "has_log": bool(has_log),
        "id": str(row.id),
        "task_id": str(row.task_id),
        "instance_id": row.instance_id,
        "offer_id": row.offer_id,
        "machine_id": row.machine_id,
        "gpu_name": row.gpu_name,
        "price_per_hour": row.price_per_hour,
        "attempt": row.attempt,
        "state": row.state,
        "status_msg": row.status_msg,
        "log_tail": (row.log_tail or "")[-1200:] or None,
        "destroy_reason": row.destroy_reason,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "ready_at": row.ready_at.isoformat() if row.ready_at else None,
        "destroyed_at": row.destroyed_at.isoformat() if row.destroyed_at else None,
    }


@router.get("/instances")
async def list_worker_instances(
    active_only: bool = False,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    query = select(WorkerInstance).order_by(WorkerInstance.created_at.desc()).limit(
        max(1, min(200, limit))
    )
    if active_only:
        query = query.where(WorkerInstance.state != "destroyed")
    rows = (await db.execute(query)).scalars().all()
    instance_ids = [row.instance_id for row in rows if row.instance_id is not None]
    logged: set[int] = set()
    if instance_ids:
        logged = set(
            (
                await db.execute(
                    select(WorkerLog.instance_id).where(WorkerLog.instance_id.in_(instance_ids))
                )
            )
            .scalars()
            .all()
        )
    return {
        "items": [_serialize(row, has_log=row.instance_id in logged) for row in rows],
        "count": len(rows),
    }


@router.get("/live")
async def live_worker_instances(
    current_user: User = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Instance yang benar-benar ada di akun Vast (live), termasuk disk/GPU util."""
    try:
        items = await vast_admin.live_instances()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"items": items, "count": len(items)}


@router.get("/instances/{instance_id}/logs")
async def worker_instance_logs(
    instance_id: int,
    tail: int = 1000,
    daemon: bool = False,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Log container instance (fallback ke log_tail lokal bila instance sudah hilang)."""
    row = (
        await db.execute(
            select(WorkerInstance)
            .where(WorkerInstance.instance_id == instance_id)
            .order_by(WorkerInstance.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    local_tail = (row.log_tail or "") if row else ""
    try:
        text = await vast_admin.instance_logs(instance_id, tail=tail, daemon=daemon)
    except RuntimeError as exc:
        if local_tail:
            return {
                "source": "local",
                "text": local_tail,
                "local_tail": local_tail,
                "warning": str(exc),
            }
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"source": "vast", "text": text, "local_tail": local_tail or None}


@router.get("/logs")
async def list_worker_logs(
    outcome: str = Query(default="failed", description="failed|cancelled|success|all"),
    q: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Log worker tersimpan (audit kegagalan instance GPU)."""
    return await worker_logs.list_logs(db, outcome=outcome, q=q, limit=limit)


@router.get("/logs/{log_id}")
async def read_worker_log(
    log_id: str,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    from uuid import UUID as _UUID

    try:
        parsed = _UUID(log_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid log id.")
    payload = await worker_logs.get_log(db, parsed)
    if payload is None:
        raise HTTPException(status_code=404, detail="Log worker tidak ditemukan.")
    return payload


@router.post("/logs/clear")
async def clear_worker_logs(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Hapus SEMUA log worker tersimpan (satu klik dari dashboard)."""
    result = await worker_logs.clear_all(db)
    logger.warning(
        "Admin %s menghapus semua log worker (%s baris)",
        current_user.email,
        result.get("deleted"),
    )
    return result


@router.post("/instances/{instance_id}/destroy")
async def destroy_worker_instance(
    instance_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Hapus instance secara paksa (mis. worker hang yang tidak terdeteksi)."""
    from app.services.vast_worker import _get_vast_client

    settings = get_settings()
    if not (settings.VAST_API_KEY or "").strip():
        raise HTTPException(status_code=503, detail="VAST_API_KEY belum diset")

    client = _get_vast_client()
    already_gone = False
    try:
        await asyncio.to_thread(client.destroy_instance, instance_id)
    except Exception as exc:
        # Vast membalas 404 bila instance sudah tidak ada (mis. dihapus otomatis
        # setelah container mati, atau sisa baris lama). Itu bukan kegagalan:
        # tanpa toleransi ini, baris "ghost" tidak bisa dibersihkan dari dashboard.
        if "404" in str(exc) or "not found" in str(exc).lower():
            already_gone = True
            logger.warning(
                "Instance %s sudah tidak ada di Vast (404); baris ditandai destroyed.",
                instance_id,
            )
        else:
            raise HTTPException(status_code=502, detail=f"Gagal menghapus: {exc}") from exc

    row: Optional[WorkerInstance] = (
        await db.execute(
            select(WorkerInstance)
            .where(WorkerInstance.instance_id == instance_id)
            .order_by(WorkerInstance.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        row.state = "destroyed"
        row.destroy_reason = ("admin manual (sudah tidak ada)" if already_gone else "admin manual")[:120]
        await db.commit()

    logger.warning(
        "Admin %s menghapus instance %s secara manual", current_user.email, instance_id
    )
    return {"ok": True, "instance_id": instance_id, "already_gone": already_gone}


@router.get("/lines")
async def list_worker_lines(
    task_id: Optional[str] = None,
    after_seq: int = 0,
    level: Optional[str] = None,
    limit: int = 200,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Baris log realtime dari dalam instance worker."""
    from app.services import worker_log_lines

    try:
        items = await worker_log_lines.list_lines(
            db, task_id=task_id, after_seq=after_seq, level=level, limit=limit
        )
        return {"items": items, "error": None}
    except Exception as exc:  # noqa: BLE001 - jangan 500-kan halaman admin
        return {"items": [], "error": str(exc)[:300]}


@router.post("/lines/clear")
async def clear_worker_lines(
    task_id: Optional[str] = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    from app.services import worker_log_lines

    removed = await worker_log_lines.clear(db, task_id)
    return {"ok": True, "removed": removed}


@router.get("/tasks")
async def list_worker_tasks(
    limit: int = 30,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Daftar task terakhir + status + jumlah baris log worker (untuk tabel UI)."""
    from sqlalchemy import func as _func, select as _select

    from app.models.task import Task
    from app.models.worker_log_line import WorkerLogLine

    try:
        statement = (
            _select(Task, _func.count(WorkerLogLine.id))
            .outerjoin(WorkerLogLine, WorkerLogLine.task_id == Task.id)
            .group_by(Task.id)
            .order_by(Task.created_at.desc())
            .limit(max(1, min(100, limit)))
        )
        rows = (await db.execute(statement)).all()
        items = [
            {
                "id": str(task.id),
                "status": task.status.value if task.status else None,
                "progress": task.progress,
                "download_status": task.download_status,
                "error_message": (task.error_message or "")[:200] or None,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "log_count": int(count or 0),
            }
            for task, count in rows
        ]
        return {"items": items, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"items": [], "error": str(exc)[:300]}
