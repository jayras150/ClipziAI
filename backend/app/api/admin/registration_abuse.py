"""Admin API - Registration Abuse / device reputation (Fase 1/2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.device import (
    DEVICE_STATUS_NEW,
    DEVICE_STATUS_TRUSTED,
    Device,
    DeviceAccount,
    DeviceEvent,
    DeviceFreeClaim,
)
from app.models.user import User
from app.services import device_reputation

router = APIRouter(dependencies=[Depends(get_current_admin)])


class DeviceSettingsIn(BaseModel):
    enforce_device_claim: Optional[bool] = None
    signup_bonus: Optional[int] = None


def _audit(
    db: AsyncSession,
    request: Request,
    admin: User,
    action: str,
    resource_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="device_reputation",
            resource_id=resource_id,
            meta_data=meta or {},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


async def _device_payload(db: AsyncSession, device: Device) -> Dict[str, Any]:
    account_rows = (
        await db.execute(
            select(DeviceAccount, User)
            .join(User, User.id == DeviceAccount.user_id)
            .where(DeviceAccount.device_id == device.id)
            .order_by(DeviceAccount.created_at.asc())
        )
    ).all()
    accounts = [
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "linked_at": link.created_at.isoformat() if link.created_at else None,
        }
        for link, user in account_rows
    ]
    claim = (
        await db.execute(
            select(DeviceFreeClaim).where(DeviceFreeClaim.device_id == device.id)
        )
    ).scalar_one_or_none()
    event_count = (
        await db.execute(
            select(func.count(DeviceEvent.id)).where(DeviceEvent.device_id == device.id)
        )
    ).scalar() or 0
    return {
        "id": str(device.id),
        "fingerprint_preview": device.fingerprint_hash[:12],
        "fingerprint_hash": device.fingerprint_hash,
        "reputation_score": int(device.reputation_score or 0),
        "reputation_status": device.reputation_status,
        "manual_trusted": bool((device.metadata_json or {}).get("manual_trust")),
        "first_seen": device.first_seen.isoformat() if device.first_seen else None,
        "last_seen": device.last_seen.isoformat() if device.last_seen else None,
        "last_ip_hash": device.last_ip_hash,
        "last_user_agent": device.last_user_agent,
        "account_count": len(accounts),
        "claim_count": 1 if claim else 0,
        "claim": (
            {
                "amount": claim.amount,
                "status": claim.status,
                "claimed_at": claim.claimed_at.isoformat() if claim.claimed_at else None,
                "user_id": str(claim.user_id) if claim.user_id else None,
            }
            if claim
            else None
        ),
        "accounts": accounts,
        "event_count": int(event_count),
    }


@router.get("")
async def list_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    count_query = select(func.count(Device.id))
    query = select(Device)
    if status:
        count_query = count_query.where(Device.reputation_status == status.upper())
        query = query.where(Device.reputation_status == status.upper())
    total = int((await db.execute(count_query)).scalar() or 0)
    rows = (
        (
            await db.execute(
                query.order_by(Device.last_seen.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [await _device_payload(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "config": await device_reputation.get_device_config(db),
    }

@router.get("/{device_id}")
async def read_device(
    device_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan.")
    payload = await _device_payload(db, device)
    events = (
        (
            await db.execute(
                select(DeviceEvent)
                .where(DeviceEvent.device_id == device.id)
                .order_by(DeviceEvent.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    payload["events"] = [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "risk_score": event.risk_score,
            "user_id": str(event.user_id) if event.user_id else None,
            "ip_hash": event.ip_hash,
            "user_agent": event.user_agent,
            "metadata": event.metadata_json,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event in events
    ]
    return payload


@router.post("/{device_id}/trust")
async def trust_device(
    device_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan.")
    before = device.reputation_status
    device.reputation_status = DEVICE_STATUS_TRUSTED
    device.reputation_score = 0
    device.metadata_json = {
        **(device.metadata_json or {}),
        "manual_trust": True,
        "trusted_at": datetime.utcnow().isoformat(),
    }
    _audit(
        db,
        request,
        current_admin,
        "device_trusted",
        str(device.id),
        {"from": before, "to": DEVICE_STATUS_TRUSTED},
    )
    await db.commit()
    return {"ok": True, **(await _device_payload(db, device))}


@router.post("/{device_id}/reset-claim")
async def reset_claim(
    device_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan.")
    result = await db.execute(
        delete(DeviceFreeClaim).where(DeviceFreeClaim.device_id == device.id)
    )
    device.reputation_status = DEVICE_STATUS_NEW
    device.reputation_score = 0
    device.metadata_json = {
        **(device.metadata_json or {}),
        "manual_trust": False,
    }
    _audit(
        db,
        request,
        current_admin,
        "device_claim_reset",
        str(device.id),
        {"removed_claims": int(result.rowcount or 0)},
    )
    await db.commit()
    return {"ok": True, **(await _device_payload(db, device))}


@router.put("/settings")
async def update_settings(
    payload: DeviceSettingsIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    data = payload.model_dump(exclude_none=True)
    config = await device_reputation.set_device_config(db, data)
    _audit(
        db,
        request,
        current_admin,
        "device_reputation_settings_updated",
        meta=config,
    )
    await db.commit()
    return {"ok": True, "config": config}

