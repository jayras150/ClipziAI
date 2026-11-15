"""Device reputation + one-time free-credit claim (Fase 1/2).

Fase 1: semua registrasi tetap mendapat bonus; keputusan hanya dicatat.
Fase 2: `enforce_device_claim=true` menolak bonus kedua dari fingerprint yang sama.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.models.device import (
    DEVICE_STATUS_HIGH,
    DEVICE_STATUS_LOW,
    DEVICE_STATUS_NEW,
    DEVICE_STATUS_SUSPICIOUS,
    DEVICE_STATUS_TRUSTED,
    Device,
    DeviceAccount,
    DeviceEvent,
    DeviceFreeClaim,
)
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services import platform_settings as ps

logger = logging.getLogger(__name__)

DEVICE_SETTING_KEY = "device_reputation"
DEFAULT_DEVICE_SETTING: Dict[str, Any] = {
    "enforce_device_claim": False,
    "signup_bonus": 5,
}


def _secret() -> str:
    settings = get_settings()
    return str(getattr(settings, "DEVICE_FINGERPRINT_SECRET", "") or settings.SECRET_KEY)


def normalize_fingerprint(value: Optional[str]) -> str:
    return str(value or "").strip()[:512]


def hash_fingerprint(value: Optional[str]) -> str:
    raw = normalize_fingerprint(value)
    return hmac.new(_secret().encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_ip(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()[:80]
    if not text:
        return None
    return hmac.new(_secret().encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    """Ambil IP dari proxy tepercaya; fallback ke koneksi langsung."""
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value[:80]
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded[:80]
    return (request.client.host if request.client else "")[:80]


def client_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:500]


def risk_status(score: int) -> str:
    if score >= 80:
        return DEVICE_STATUS_HIGH
    if score >= 50:
        return DEVICE_STATUS_SUSPICIOUS
    if score >= 21:
        return DEVICE_STATUS_LOW
    if score >= 0:
        return DEVICE_STATUS_NEW
    return DEVICE_STATUS_NEW


def calculate_risk_score(
    *,
    account_count: int,
    claim_count: int,
    email_verified: bool,
    has_fingerprint: bool,
) -> int:
    """Skor fase 1/2: hanya bukti device/account, tanpa IP intelligence."""
    score = 0
    if account_count > 1:
        score += 40
    if account_count >= 3:
        score += 30
    if claim_count > 0:
        score += 30
    if not has_fingerprint:
        score += 20
    if email_verified:
        score -= 10
    return max(0, min(100, score))


def normalize_device_setting(raw: Any) -> Dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    try:
        bonus = int(value.get("signup_bonus", DEFAULT_DEVICE_SETTING["signup_bonus"]))
    except (TypeError, ValueError):
        bonus = int(DEFAULT_DEVICE_SETTING["signup_bonus"])
    return {
        "enforce_device_claim": bool(value.get("enforce_device_claim", False)),
        "signup_bonus": max(0, min(100, bonus)),
    }


async def get_device_config(db: AsyncSession) -> Dict[str, Any]:
    raw = await ps.get_setting(db, DEVICE_SETTING_KEY, {})
    return normalize_device_setting(raw)


async def set_device_config(db: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    current = await get_device_config(db)
    merged = {
        "enforce_device_claim": bool(
            payload.get("enforce_device_claim", current["enforce_device_claim"])
        ),
        "signup_bonus": payload.get("signup_bonus", current["signup_bonus"]),
    }
    config = normalize_device_setting(merged)
    await ps.set_setting(db, DEVICE_SETTING_KEY, config)
    return config

async def get_or_create_device(
    db: AsyncSession,
    fingerprint: str,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[Device]:
    normalized = normalize_fingerprint(fingerprint)
    if not normalized:
        return None
    fingerprint_hash = hash_fingerprint(normalized)
    device = (
        await db.execute(select(Device).where(Device.fingerprint_hash == fingerprint_hash))
    ).scalar_one_or_none()
    if device is None:
        try:
            async with db.begin_nested():
                device = Device(
                    fingerprint_hash=fingerprint_hash,
                    reputation_status=DEVICE_STATUS_NEW,
                    reputation_score=0,
                )
                db.add(device)
                await db.flush()
        except IntegrityError:
            device = (
                await db.execute(
                    select(Device).where(Device.fingerprint_hash == fingerprint_hash)
                )
            ).scalar_one_or_none()
    if device is None:
        return None
    device.last_seen = datetime.utcnow()
    device.last_ip_hash = hash_ip(ip)
    device.last_user_agent = (user_agent or "")[:500] or None
    return device


async def associate_account(db: AsyncSession, device: Device, user_id: UUID) -> None:
    exists = (
        await db.execute(
            select(DeviceAccount.id).where(
                DeviceAccount.device_id == device.id,
                DeviceAccount.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if exists:
        return
    try:
        async with db.begin_nested():
            db.add(DeviceAccount(device_id=device.id, user_id=user_id))
            await db.flush()
    except IntegrityError:
        return


async def _account_count(db: AsyncSession, device_id: UUID) -> int:
    value = (
        await db.execute(
            select(func.count(DeviceAccount.id)).where(DeviceAccount.device_id == device_id)
        )
    ).scalar()
    return int(value or 0)


async def _claim_count(db: AsyncSession, device_id: UUID) -> int:
    value = (
        await db.execute(
            select(func.count(DeviceFreeClaim.id)).where(DeviceFreeClaim.device_id == device_id)
        )
    ).scalar()
    return int(value or 0)

async def _grant_bonus(db: AsyncSession, user: User, amount: int) -> int:
    if amount <= 0:
        return 0
    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        return 0
    profile.credits_balance = int(profile.credits_balance or 0) + amount
    profile.credits_total_earned = int(profile.credits_total_earned or 0) + amount
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=amount,
            type=CreditTransactionType.SIGNUP_BONUS,
            description={"en": "Signup bonus", "id": "Bonus pendaftaran"},
            balance_after=profile.credits_balance,
        )
    )
    return amount


async def _add_event(
    db: AsyncSession,
    *,
    event_type: str,
    device_id: Optional[UUID],
    user_id: Optional[UUID],
    risk: int,
    ip: Optional[str],
    user_agent: Optional[str],
    meta: Optional[dict] = None,
) -> None:
    db.add(
        DeviceEvent(
            device_id=device_id,
            user_id=user_id,
            event_type=event_type,
            risk_score=risk,
            ip_hash=hash_ip(ip),
            user_agent=(user_agent or "")[:500] or None,
            metadata_json=meta or {},
        )
    )

async def claim_signup_bonus(
    db: AsyncSession,
    user: User,
    fingerprint: Optional[str],
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Dict[str, Any]:
    """Klaim bonus signup; caller wajib melakukan commit setelahnya."""
    config = await get_device_config(db)
    normalized = normalize_fingerprint(fingerprint)
    has_fingerprint = bool(normalized)
    device = await get_or_create_device(db, normalized, ip=ip, user_agent=user_agent)

    account_count = 0
    claim_count = 0
    claimed = False
    if device is not None:
        await associate_account(db, device, user.id)
        account_count = await _account_count(db, device.id)
        claim_count = await _claim_count(db, device.id)
        try:
            async with db.begin_nested():
                db.add(
                    DeviceFreeClaim(
                        device_id=device.id,
                        user_id=user.id,
                        amount=int(config["signup_bonus"]),
                        status="claimed",
                    )
                )
                await db.flush()
            claimed = True
            claim_count = await _claim_count(db, device.id)
        except IntegrityError:
            claimed = False

    enforce = bool(config["enforce_device_claim"])
    should_grant = (not enforce) if not has_fingerprint else (claimed or not enforce)
    amount = int(config["signup_bonus"]) if should_grant else 0
    granted = await _grant_bonus(db, user, amount)

    risk = calculate_risk_score(
        account_count=account_count,
        claim_count=claim_count,
        email_verified=bool(user.email_verified),
        has_fingerprint=has_fingerprint,
    )
    status = risk_status(risk)
    if device is not None:
        if (device.metadata_json or {}).get("manual_trust"):
            device.reputation_score = 0
            device.reputation_status = DEVICE_STATUS_TRUSTED
        else:
            device.reputation_score = risk
            device.reputation_status = status

    if not has_fingerprint:
        event_type = "missing_fingerprint"
        reason = "missing_fingerprint"
    elif claimed:
        event_type = "signup_bonus_granted"
        reason = "new_device_claim"
    elif enforce:
        event_type = "signup_bonus_denied"
        reason = "device_already_claimed"
    else:
        event_type = "signup_bonus_shadow_duplicate"
        reason = "shadow_mode_duplicate"

    await _add_event(
        db,
        event_type=event_type,
        device_id=device.id if device else None,
        user_id=user.id,
        risk=risk,
        ip=ip,
        user_agent=user_agent,
        meta={
            "account_count": account_count,
            "claim_count": claim_count,
            "enforce": enforce,
            "bonus_requested": int(config["signup_bonus"]),
        },
    )
    return {
        "granted": granted > 0,
        "amount": granted,
        "reason": reason,
        "risk_score": risk,
        "status": status,
        "device_id": str(device.id) if device else None,
        "account_count": account_count,
        "claim_count": claim_count,
    }

async def associate_login(
    db: AsyncSession,
    user: User,
    fingerprint: Optional[str],
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    normalized = normalize_fingerprint(fingerprint)
    device = await get_or_create_device(db, normalized, ip=ip, user_agent=user_agent)
    if device is None:
        return
    await associate_account(db, device, user.id)
    account_count = await _account_count(db, device.id)
    claim_count = await _claim_count(db, device.id)
    risk = calculate_risk_score(
        account_count=account_count,
        claim_count=claim_count,
        email_verified=bool(user.email_verified),
        has_fingerprint=True,
    )
    if (device.metadata_json or {}).get("manual_trust"):
        device.reputation_score = 0
        device.reputation_status = DEVICE_STATUS_TRUSTED
    else:
        device.reputation_score = risk
        device.reputation_status = risk_status(risk)
    await _add_event(
        db,
        event_type="login",
        device_id=device.id,
        user_id=user.id,
        risk=risk,
        ip=ip,
        user_agent=user_agent,
        meta={"account_count": account_count, "claim_count": claim_count},
    )


__all__ = [
    "DEVICE_SETTING_KEY",
    "DEFAULT_DEVICE_SETTING",
    "associate_login",
    "calculate_risk_score",
    "claim_signup_bonus",
    "client_ip",
    "client_user_agent",
    "get_device_config",
    "get_or_create_device",
    "hash_fingerprint",
    "normalize_device_setting",
    "normalize_fingerprint",
    "risk_status",
    "set_device_config",
]




