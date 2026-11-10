"""
Admin audit log endpoints
"""
from fastapi import APIRouter, Depends
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.audit_log import AuditLog, ActorType

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=List[dict])
async def get_audit_logs(
    db: AsyncSession = Depends(get_db_session),
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
):
    query = select(AuditLog)
    
    if actor_type:
        query = query.where(AuditLog.actor_type == actor_type)
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
    
    result = await db.execute(query.order_by(AuditLog.created_at.desc()).limit(limit))
    logs = result.scalars().all()
    
    return [
        {
            "id": str(l.id),
            "actor_type": l.actor_type.value,
            "actor_id": str(l.actor_id),
            "actor_email": l.actor_email,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/user/{user_id}/timeline", response_model=List[dict])
async def get_user_activity_timeline(
    user_id: str,
    db: AsyncSession = Depends(get_db_session),
    limit: int = 100,
):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.actor_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    
    return [
        {
            "id": str(l.id),
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "metadata": l.meta_data,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]