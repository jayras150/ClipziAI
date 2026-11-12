"""
Admin audit log: daftar dengan filter + detail (untuk melihat diff nilai).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import AuditLog

router = APIRouter(dependencies=[Depends(get_current_admin)])


def _serialize(log: AuditLog, detail: bool = False) -> dict:
    payload = {
        "id": str(log.id),
        "actor_type": getattr(log.actor_type, "value", str(log.actor_type)),
        "actor_id": str(log.actor_id),
        "actor_email": log.actor_email,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "ip_address": log.ip_address,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
    if detail:
        payload.update(
            {
                "resource_name": log.resource_name,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "metadata": log.meta_data,
                "user_agent": log.user_agent,
            }
        )
    return payload


@router.get("/")
async def get_audit_logs(
    actor_type: Optional[str] = None,
    action: Optional[str] = Query(default=None, description="Substring nama aksi"),
    resource_type: Optional[str] = None,
    q: Optional[str] = Query(default=None, description="Cari aksi / email / resource id"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=300),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(AuditLog)
    if actor_type:
        query = query.where(AuditLog.actor_type == actor_type)
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                AuditLog.action.ilike(like),
                func.coalesce(AuditLog.actor_email, "").ilike(like),
                func.coalesce(AuditLog.resource_id, "").ilike(like),
            )
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "items": [_serialize(log) for log in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/actions")
async def list_actions(db: AsyncSession = Depends(get_db_session)):
    """Daftar nama aksi unik (untuk dropdown filter)."""
    rows = (
        await db.execute(select(AuditLog.action, func.count()).group_by(AuditLog.action).order_by(AuditLog.action))
    ).all()
    return [{"action": action, "count": int(count)} for action, count in rows]


@router.get("/detail/{log_id}")
async def get_audit_detail(log_id: UUID, db: AsyncSession = Depends(get_db_session)):
    log = (await db.execute(select(AuditLog).where(AuditLog.id == log_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log tidak ditemukan")
    return _serialize(log, detail=True)


@router.get("/user/{user_id}/timeline")
async def get_user_activity_timeline(
    user_id: str,
    limit: int = Query(default=100, ge=1, le=300),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.actor_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [_serialize(log, detail=True) for log in result.scalars().all()]
