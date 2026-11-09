"""
User endpoints - Profile, credits, plan
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.user import (
    UserProfileResponse,
    UserUpdate,
    PasswordChange,
    CreditBalanceResponse,
)

router = APIRouter()


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return UserProfileResponse(
        id=str(profile.id),
        email=current_user.email,
        name=current_user.name,
        avatar_url=current_user.avatar_url,
        plan_type=profile.plan_type.value,
        credits_balance=profile.credits_balance,
        credits_total_earned=profile.credits_total_earned,
        credits_total_spent=profile.credits_total_spent,
        language=profile.language,
        timezone=profile.timezone,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
        two_factor_enabled=current_user.two_factor_enabled,
        created_at=profile.created_at,
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if update_data.name:
        current_user.name = update_data.name
    
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    if profile is None:
        raise HTTPException(status_code=404, detail="User profile not found")

    if update_data.language:
        profile.language = update_data.language
    if update_data.timezone:
        profile.timezone = update_data.timezone

    await db.commit()
    
    return UserProfileResponse(
        id=str(profile.id),
        email=current_user.email,
        name=current_user.name,
        avatar_url=current_user.avatar_url,
        plan_type=profile.plan_type.value,
        credits_balance=profile.credits_balance,
        credits_total_earned=profile.credits_total_earned,
        credits_total_spent=profile.credits_total_spent,
        language=profile.language,
        timezone=profile.timezone,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
        two_factor_enabled=current_user.two_factor_enabled,
        created_at=profile.created_at,
    )


@router.put("/password")
async def change_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Ganti kata sandi akun.

    Akun yang dibuat lewat Google belum punya password, jadi `current_password`
    hanya diwajibkan bila password sudah pernah diset.
    """
    new_password = (payload.new_password or "").strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")

    if current_user.password_hash:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="Current password is required.")
        if not verify_password(payload.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")

    current_user.password_hash = hash_password(new_password)
    await db.commit()

    return {"message": "Password updated successfully."}


@router.get("/credits", response_model=CreditBalanceResponse)

async def get_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return CreditBalanceResponse(
        credits_balance=profile.credits_balance,
        credits_total_earned=profile.credits_total_earned,
        credits_total_spent=profile.credits_total_spent,
        plan_type=profile.plan_type.value,
    )