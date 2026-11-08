"""
Authentication endpoints - Register, login, 2FA, social, password reset
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    generate_totp_secret, get_totp_uri, generate_backup_codes, verify_totp,
    decode_token
)
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.pricing_plan import PricingPlan
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, RefreshTokenRequest,
    ForgotPasswordRequest, ResetPasswordRequest, TwoFactorSetup, TwoFactorVerify,
    SocialLoginRequest
)
from app.schemas.user import UserProfileResponse, CreditBalanceResponse
from app.core.config import get_settings

router = APIRouter()
security = HTTPBearer()
settings = get_settings()


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db_session)):
    # Check if user exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Get free plan
    result = await db.execute(select(PricingPlan).where(PricingPlan.name == "free"))
    free_plan = result.scalar_one_or_none()
    
    # Create user
    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        name=user_data.name,
        provider="email",
    )
    db.add(user)
    await db.flush()
    
    # Create profile
    profile = UserProfile(
        user_id=user.id,
        plan_type=free_plan.name if free_plan else "free",
        credits_balance=5,  # Signup bonus
        credits_total_earned=5,
        max_concurrent_tasks=free_plan.max_concurrent_tasks if free_plan else 1,
        watermark_enabled=free_plan.watermark if free_plan else True,
    )
    db.add(profile)
    
    # Credit transaction for signup bonus
    credit_tx = CreditTransaction(
        user_id=user.id,
        amount=5,
        type=CreditTransactionType.SIGNUP_BONUS,
        description={"en": "Signup bonus", "id": "Bonus pendaftaran"},
        balance_after=5,
    )
    db.add(credit_tx)
    
    await db.commit()
    
    # Generate tokens
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()
    
    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")
    
    # Update last login
    user.last_login_at = __import__("datetime").datetime.utcnow()
    await db.commit()
    
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db_session)):
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    
    access_token = create_access_token({"sub": str(user.id)})
    new_refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/2fa/setup", response_model=TwoFactorSetup)
async def setup_2fa(
    current_user: User = Depends(lambda: None),  # Will be wired with proper auth
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Wire with get_current_user dependency once auth middleware is complete
    secret = generate_totp_secret()
    backup_codes = generate_backup_codes()
    
    return TwoFactorSetup(
        secret=secret,
        qr_code_url=get_totp_uri("user@clipzi.ai", secret),
        backup_codes=backup_codes,
    )


@router.post("/2fa/verify")
async def verify_2fa(data: TwoFactorVerify):
    valid = verify_totp(data.secret, data.otp)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid OTP code")
    return {"verified": True}


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    # TODO: Send reset email via SMTP
    return {"message": "If email exists, reset link has been sent"}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    # TODO: Verify token and reset password
    return {"message": "Password has been reset"}


@router.post("/social-login")
async def social_login(data: SocialLoginRequest, db: AsyncSession = Depends(get_db_session)):
    # TODO: Implement Google, X, Facebook OAuth verification
    return {"message": f"Social login via {data.provider} - implementation pending"}