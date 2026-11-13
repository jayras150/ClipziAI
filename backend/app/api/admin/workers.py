"""
Admin: monitor instance GPU Vast.ai (riwayat + aksi hapus paksa).

Berguna saat worker gagal boot: admin bisa melihat mesin mana yang bermasalah,
berapa percobaan, harga, dan potongan log terakhir tanpa membuka dashboard Vast.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.core.config import get_settings
from app.models.user import User
from app.models.worker_instance import WorkerInstance

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(row: WorkerInstance) -> Dict[str, Any]:
    return {
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
    return {"items": [_serialize(row) for row in rows], "count": len(rows)}


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
