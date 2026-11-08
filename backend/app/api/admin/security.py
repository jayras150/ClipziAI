"""
Admin security events endpoints
"""
from fastapi import APIRouter, Depends
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.security_event import SecurityEvent

router = APIRouter()


@router.get("/", response_model=List[dict])
async def get_security_events(
    db: AsyncSession = Depends(get_db_session),
    risk_level: Optional[str] = None,
    limit: int = 100,
):
    query = select(SecurityEvent)
    
    if risk_level:
        query = query.where(SecurityEvent.risk_level == risk_level)
    
    result = await db.execute(query.order_by(SecurityEvent.created_at.desc()).limit(limit))
    events = result.scalars().all()
    
    return [
        {
            "id": str(e.id),
            "event_type": e.event_type.value,
            "actor_type": e.actor_type,
            "actor_id": str(e.actor_id) if e.actor_id else None,
            "ip_address": e.ip_address,
            "risk_level": e.risk_level.value,
            "is_resolved": e.is_resolved,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]