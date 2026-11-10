"""
Admin user management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID

from app.api.deps import get_db_session
from app.models.admin_user import AdminUser
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.credit_transaction import CreditTransaction, CreditTransactionType

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=List[dict])
async def list_users(
    db: AsyncSession = Depends(get_db_session),
    current_admin: AdminUser = Depends(get_current_admin),
):
    result = await db.execute(select(User))
    users = result.scalars().all()
    
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "provider": u.provider.value,
            "is_active": u.is_active,
            "is_banned": u.is_banned,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/{user_id}/ban")
async def ban_user(
    user_id: UUID,
    reason: str,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = True
    user.ban_reason = reason
    await db.commit()
    
    return {"message": f"User {user_id} has been banned"}


@router.post("/{user_id}/unban")
async def unban_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_banned = False
    user.ban_reason = None
    await db.commit()
    
    return {"message": f"User {user_id} has been unbanned"}


@router.post("/{user_id}/credits/adjust")
async def adjust_user_credits(
    user_id: UUID,
    amount: int,
    description: str,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.credits_balance += amount
    profile.credits_total_earned += max(0, amount)
    profile.credits_total_spent += max(0, -amount)
    
    credit_tx = CreditTransaction(
        user_id=user_id,
        amount=amount,
        type=CreditTransactionType.ADMIN_ADJUSTMENT,
        description={"en": description, "id": description},
        balance_after=profile.credits_balance,
        admin_id=None,  # Will be set from current_admin
    )
    
    db.add(credit_tx)
    await db.commit()
    
    return {"message": f"Credits adjusted by {amount}", "new_balance": profile.credits_balance}