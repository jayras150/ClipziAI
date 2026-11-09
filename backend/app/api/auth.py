"""
Authentication endpoints - Register, login, 2FA, social, password reset
"""
import httpx
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
from app.models.user import User, AuthProvider
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


GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SIGNUP_BONUS_CREDITS = 5


async def _fetch_google_profile(access_token: str) -> dict:
    """Validasi access token Google lalu kembalikan profil (email, nama, avatar)."""
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing Google access token")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError as exc:  # jaringan bermasalah
        raise HTTPException(
            status_code=502, detail=f"Could not reach Google: {exc.__class__.__name__}"
        )

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google token is invalid or expired")

    return response.json()


async def _create_oauth_user(
    db: AsyncSession, email: str, name: str, provider: AuthProvider, provider_id: str | None,
    avatar_url: str | None,
) -> User:
    """Buat user baru dari OAuth + profil + bonus kredit pendaftaran."""
    result = await db.execute(select(PricingPlan).where(PricingPlan.name == "free"))
    free_plan = result.scalar_one_or_none()

    user = User(
        email=email,
        password_hash=None,
        name=name or email.split("@")[0],
        avatar_url=avatar_url,
        provider=provider,
        provider_id=provider_id,
        email_verified=True,
    )
    db.add(user)
    await db.flush()

    db.add(
        UserProfile(
            user_id=user.id,
            plan_type=free_plan.name if free_plan else "free",
            credits_balance=SIGNUP_BONUS_CREDITS,
            credits_total_earned=SIGNUP_BONUS_CREDITS,
            max_concurrent_tasks=free_plan.max_concurrent_tasks if free_plan else 1,
            watermark_enabled=free_plan.watermark if free_plan else True,
        )
    )
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=SIGNUP_BONUS_CREDITS,
            type=CreditTransactionType.SIGNUP_BONUS,
            description={"en": "Signup bonus", "id": "Bonus pendaftaran"},
            balance_after=SIGNUP_BONUS_CREDITS,
        )
    )
    await db.commit()
    return user


@router.post("/social-login", response_model=TokenResponse)
async def social_login(data: SocialLoginRequest, db: AsyncSession = Depends(get_db_session)):
    """
    Login via penyedia OAuth.

    Alur: frontend meminta access token ke penyedia (Google Identity Services),
    lalu mengirimkannya ke endpoint ini. Backend memverifikasi token langsung ke
    server penyedia sebelum membuat/menautkan akun dan menerbitkan JWT sendiri.
    """
    provider = (data.provider or "").strip().lower()

    if provider == "google":
        profile = await _fetch_google_profile(data.access_token)
        email = (profile.get("email") or "").strip().lower()
        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email address")
        if profile.get("email_verified") is False:
            raise HTTPException(status_code=403, detail="Google email is not verified")
        name = profile.get("name") or email.split("@")[0]
        provider_id = profile.get("sub")
        avatar_url = profile.get("picture")
        auth_provider = AuthProvider.GOOGLE
    elif provider in {"x", "twitter", "facebook"}:
        raise HTTPException(
            status_code=501,
            detail=(
                f"{provider.capitalize()} sign-in is not enabled yet. "
                "Use email or Google sign-in for now."
            ),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = await _create_oauth_user(
            db, email=email, name=name, provider=auth_provider,
            provider_id=provider_id, avatar_url=avatar_url,
        )
    else:
        if user.is_banned:
            raise HTTPException(status_code=403, detail=user.ban_reason or "Account suspended")
        # Tautkan provider agar login berikutnya konsisten.
        if user.provider != auth_provider:
            user.provider = auth_provider
        if provider_id and not user.provider_id:
            user.provider_id = provider_id
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        if not user.email_verified:
            user.email_verified = True
        await db.commit()

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
