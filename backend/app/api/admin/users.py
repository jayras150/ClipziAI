"""
Admin user management: daftar, detail, edit, ban/suspend, kredit, plan,
reset password, paksa logout, serta aktivitas (tasks/transaksi/log).

Catatan penting dibanding versi lama:
  - Body memakai JSON (dulu `reason`, `amount`, `description` adalah query
    param WAJIB sehingga tombol di dashboard gagal dengan 422).
  - Setiap aksi tulis dicatat ke `audit_logs` dengan pelaku admin.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.core.security import hash_password
from app.models.audit_log import ActorType, AuditLog
from app.models.clip import Clip
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.models.task import Task
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.models.user_profile import PlanType, UserProfile
from app.services.auth_session import revoke_sessions

router = APIRouter(dependencies=[Depends(get_current_admin)])


class UserUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None


class BanIn(BaseModel):
    reason: str = Field(default="Pelanggaran ketentuan layanan", max_length=500)


class SuspendIn(BaseModel):
    reason: str = Field(default="Ditangguhkan sementara", max_length=500)
    until: Optional[datetime] = None


class CreditsAdjustIn(BaseModel):
    amount: int = Field(description="Positif menambah, negatif mengurangi")
    description: str = Field(default="Penyesuaian oleh admin", max_length=255)


class PlanIn(BaseModel):
    plan: str = Field(description="free | standar | pro | team")
    expires_at: Optional[datetime] = None
    reset_credits: Optional[int] = Field(default=None, ge=0)


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    return user


async def _get_profile(db: AsyncSession, user_id: UUID) -> Optional[UserProfile]:
    return (
        await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    ).scalar_one_or_none()


async def _audit(
    db: AsyncSession,
    request: Request,
    admin: User,
    action: str,
    resource_id: str,
    old: Optional[dict] = None,
    new: Optional[dict] = None,
    meta: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="user",
            resource_id=resource_id,
            old_values=old,
            new_values=new,
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


def _plan_value(profile: Optional[UserProfile]) -> str:
    if not profile:
        return PlanType.FREE.value
    plan = profile.plan_type
    return getattr(plan, "value", str(plan))


@router.get("/")
async def list_users(
    q: Optional[str] = Query(default=None, description="Cari email atau nama"),
    status: Optional[str] = Query(default=None, description="active | banned | inactive"),
    plan: Optional[str] = Query(default=None, description="free | standar | pro | team"),
    sort: str = Query(default="-created_at"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(User, UserProfile).outerjoin(UserProfile, UserProfile.user_id == User.id)

    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(User.email.ilike(like), User.name.ilike(like)))
    if status == "banned":
        query = query.where(User.is_banned.is_(True))
    elif status == "inactive":
        query = query.where(User.is_active.is_(False))
    elif status == "active":
        query = query.where(User.is_active.is_(True), User.is_banned.is_(False))
    if plan:
        try:
            query = query.where(UserProfile.plan_type == PlanType(plan.lower()))
        except ValueError:
            raise HTTPException(status_code=400, detail="Plan tidak dikenal")

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    sort_column = {
        "created_at": User.created_at,
        "-created_at": User.created_at.desc(),
        "email": User.email,
        "-email": User.email.desc(),
        "name": User.name,
        "-name": User.name.desc(),
    }.get(sort, User.created_at.desc())

    rows = (
        await db.execute(query.order_by(sort_column).offset((page - 1) * page_size).limit(page_size))
    ).all()

    items = [
        {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "provider": getattr(user.provider, "value", str(user.provider)),
            "is_active": user.is_active,
            "is_banned": user.is_banned,
            "ban_reason": user.ban_reason,
            "email_verified": user.email_verified,
            "plan": _plan_value(profile),
            "credits_balance": profile.credits_balance if profile else 0,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        for user, profile in rows
    ]

    return {"items": items, "total": int(total), "page": page, "page_size": page_size}


@router.get("/{user_id}")
async def get_user_detail(user_id: UUID, db: AsyncSession = Depends(get_db_session)):
    user = await _get_user_or_404(db, user_id)
    profile = await _get_profile(db, user_id)

    tasks_total = (
        await db.execute(select(func.count(Task.id)).where(Task.user_id == user_id))
    ).scalar() or 0
    tasks_completed = (
        await db.execute(
            select(func.count(Task.id)).where(Task.user_id == user_id, Task.status == "completed")
        )
    ).scalar() or 0
    clips_total = (
        await db.execute(
            select(func.count(Clip.id))
            .join(Task, Clip.task_id == Task.id)
            .where(Task.user_id == user_id)
        )
    ).scalar() or 0
    credits_spent = (
        await db.execute(
            select(func.coalesce(func.sum(Task.credits_spent), 0)).where(Task.user_id == user_id)
        )
    ).scalar() or 0
    revenue = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user_id,
                Transaction.status == TransactionStatus.SUCCESS.value,
            )
        )
    ).scalar() or 0

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "avatar_url": user.avatar_url,
        "provider": getattr(user.provider, "value", str(user.provider)),
        "is_active": user.is_active,
        "is_banned": user.is_banned,
        "ban_reason": user.ban_reason,
        "email_verified": user.email_verified,
        "two_factor_enabled": user.two_factor_enabled,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_login_ip": user.last_login_ip,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "profile": {
            "plan": _plan_value(profile),
            "credits_balance": profile.credits_balance if profile else 0,
            "credits_total_earned": profile.credits_total_earned if profile else 0,
            "credits_total_spent": profile.credits_total_spent if profile else 0,
            "credits_used_this_month": profile.credits_used_this_month if profile else 0,
            "subscription_expires_at": (
                profile.subscription_expires_at.isoformat()
                if profile and profile.subscription_expires_at
                else None
            ),
            "max_concurrent_tasks": profile.max_concurrent_tasks if profile else 1,
            "watermark_enabled": profile.watermark_enabled if profile else True,
            "priority_queue": profile.priority_queue if profile else False,
            "language": profile.language if profile else "id",
            "timezone": profile.timezone if profile else "Asia/Jakarta",
        },
        "stats": {
            "tasks_total": int(tasks_total),
            "tasks_completed": int(tasks_completed),
            "clips_total": int(clips_total),
            "credits_spent": float(credits_spent),
            "revenue_paid": float(revenue),
        },
    }


@router.patch("/{user_id}")
async def update_user(
    user_id: UUID,
    payload: UserUpdateIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user = await _get_user_or_404(db, user_id)
    before = {
        "name": user.name,
        "email": user.email,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
    }

    if payload.email and payload.email.lower() != (user.email or "").lower():
        existing = (
            await db.execute(select(User).where(User.email == payload.email.lower()))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Email sudah dipakai akun lain")
        user.email = payload.email.lower()

    if payload.name is not None:
        user.name = payload.name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.email_verified is not None:
        user.email_verified = payload.email_verified

    await db.commit()
    await _audit(
        db,
        request,
        current_admin,
        "user_updated",
        str(user_id),
        old=before,
        new={
            "name": user.name,
            "email": user.email,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
        },
    )
    return {"message": "User diperbarui", "id": str(user_id)}


@router.post("/{user_id}/ban")
async def ban_user(
    user_id: UUID,
    payload: BanIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user = await _get_user_or_404(db, user_id)
    user.is_banned = True
    user.ban_reason = payload.reason
    await db.commit()
    await revoke_sessions(db, user_id, reason="user_banned")
    await _audit(
        db, request, current_admin, "user_banned", str(user_id), new={"reason": payload.reason}
    )
    return {"message": f"User {user_id} diblokir", "is_banned": True}


@router.post("/{user_id}/unban")
async def unban_user(
    user_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user = await _get_user_or_404(db, user_id)
    user.is_banned = False
    user.ban_reason = None
    await db.commit()
    await _audit(db, request, current_admin, "user_unbanned", str(user_id))
    return {"message": f"Blokir user {user_id} dibuka", "is_banned": False}


@router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: UUID,
    payload: SuspendIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user = await _get_user_or_404(db, user_id)
    user.is_active = False
    user.ban_reason = payload.reason
    await db.commit()
    await revoke_sessions(db, user_id, reason="user_suspended")
    await _audit(
        db,
        request,
        current_admin,
        "user_suspended",
        str(user_id),
        new={
            "reason": payload.reason,
            "until": payload.until.isoformat() if payload.until else None,
        },
    )
    return {"message": f"User {user_id} ditangguhkan", "is_active": False}


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    user = await _get_user_or_404(db, user_id)
    user.is_active = True
    user.is_banned = False
    user.ban_reason = None
    await db.commit()
    await _audit(db, request, current_admin, "user_activated", str(user_id))
    return {"message": f"User {user_id} diaktifkan", "is_active": True}


@router.post("/{user_id}/credits/adjust")
async def adjust_user_credits(
    user_id: UUID,
    payload: CreditsAdjustIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    profile = await _get_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil user tidak ditemukan")

    before = profile.credits_balance
    profile.credits_balance += payload.amount
    profile.credits_total_earned += max(0, payload.amount)
    profile.credits_total_spent += max(0, -payload.amount)

    db.add(
        CreditTransaction(
            user_id=user_id,
            amount=payload.amount,
            type=CreditTransactionType.ADMIN_ADJUSTMENT,
            description={"en": payload.description, "id": payload.description},
            balance_after=profile.credits_balance,
            admin_id=current_admin.id,
        )
    )
    await db.commit()
    await _audit(
        db,
        request,
        current_admin,
        "user_credits_adjusted",
        str(user_id),
        old={"credits_balance": before},
        new={"credits_balance": profile.credits_balance},
        meta={"amount": payload.amount, "description": payload.description},
    )
    return {
        "message": f"Kredit disesuaikan {payload.amount}",
        "new_balance": profile.credits_balance,
    }


@router.post("/{user_id}/plan")
async def set_user_plan(
    user_id: UUID,
    payload: PlanIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    profile = await _get_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profil user tidak ditemukan")

    try:
        plan_value = PlanType(payload.plan.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Plan tidak dikenal")

    before = _plan_value(profile)
    profile.plan_type = plan_value
    profile.subscription_expires_at = payload.expires_at
    if payload.reset_credits is not None:
        profile.credits_balance = payload.reset_credits

    await db.commit()
    await _audit(
        db,
        request,
        current_admin,
        "user_plan_changed",
        str(user_id),
        old={"plan": before},
        new={
            "plan": plan_value.value,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        },
    )
    return {
        "message": f"Plan user diubah ke {plan_value.value}",
        "plan": plan_value.value,
        "credits_balance": profile.credits_balance,
    }


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Buat password sementara. Ditampilkan sekali, minta user menggantinya."""
    import secrets
    import string

    user = await _get_user_or_404(db, user_id)
    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
    user.password_hash = hash_password(temp_password)
    user.failed_login_attempts = 0
    user.lock_until = None
    await db.commit()
    await revoke_sessions(db, user_id, reason="password_reset_by_admin")
    await _audit(db, request, current_admin, "user_password_reset", str(user_id))
    return {
        "message": "Password sementara dibuat. Sampaikan ke user lewat kanal aman.",
        "temporary_password": temp_password,
    }


@router.post("/{user_id}/force-logout")
async def force_logout_user(
    user_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    revoked_before = await revoke_sessions(db, user_id, reason="admin_force_logout")
    await _audit(
        db,
        request,
        current_admin,
        "user_force_logout",
        str(user_id),
        meta={"revoked_before": revoked_before.isoformat()},
    )
    return {"message": "Semua sesi user dicabut", "revoked_before": revoked_before.isoformat()}


@router.get("/{user_id}/tasks")
async def list_user_tasks(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    rows = (
        await db.execute(
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(Task.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(t.id),
            "source_url": t.source_url,
            "source_type": t.source_type,
            "status": getattr(t.status, "value", str(t.status)),
            "progress": t.progress,
            "total_clips": t.total_clips,
            "credits_spent": t.credits_spent,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in rows
    ]


@router.get("/{user_id}/credit-transactions")
async def list_user_credit_transactions(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    rows = (
        await db.execute(
            select(CreditTransaction)
            .where(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(c.id),
            "amount": c.amount,
            "type": getattr(c.type, "value", str(c.type)),
            "balance_after": c.balance_after,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.get("/{user_id}/transactions")
async def list_user_transactions(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_user_or_404(db, user_id)
    rows = (
        await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(t.id),
            "duitku_transaction_id": t.duitku_transaction_id,
            "amount": t.amount,
            "currency": t.currency,
            "status": getattr(t.status, "value", str(t.status)),
            "payment_method": t.payment_method,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.get("/{user_id}/timeline")
async def list_user_timeline(
    user_id: UUID,
    limit: int = Query(default=100, ge=1, le=300),
    db: AsyncSession = Depends(get_db_session),
):
    """Jejak aktivitas user dari audit_logs (aksi user maupun aksi admin padanya)."""
    await _get_user_or_404(db, user_id)
    rows = (
        await db.execute(
            select(AuditLog)
            .where(
                or_(
                    AuditLog.actor_id == user_id,
                    (AuditLog.resource_type == "user") & (AuditLog.resource_id == str(user_id)),
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": str(log.id),
            "actor_type": getattr(log.actor_type, "value", str(log.actor_type)),
            "actor_email": log.actor_email,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "metadata": log.meta_data,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in rows
    ]

