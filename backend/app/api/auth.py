"""
Authentication endpoints - Register, login, 2FA, social, password reset
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    generate_totp_secret, get_totp_uri, generate_backup_codes, verify_totp,
    decode_token
)
from app.core.auth_cookies import (
    CSRF_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from app.models.user import User, AuthProvider
from app.models.user_profile import UserProfile
from app.models.pricing_plan import PricingPlan
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, RefreshTokenRequest,
    ForgotPasswordRequest, ResetPasswordRequest, TwoFactorSetup, TwoFactorVerify,
    SocialLoginRequest
)
from app.schemas.user import UserProfileResponse, CreditBalanceResponse
from app.core.config import get_settings
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.services import mailer
from app.services import device_reputation

router = APIRouter()


def _sign_token(purpose: str, minutes: int, **extra: Any) -> str:
    import jwt
    from datetime import datetime, timedelta, timezone

    from app.core.config import get_settings

    payload = {
        "purpose": purpose,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        **extra,
    }
    return jwt.encode(payload, get_settings().SECRET_KEY, algorithm="HS256")


def _read_token(token: str, purpose: str) -> dict:
    import jwt

    from app.core.config import get_settings

    try:
        data = jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid or expired token") from exc
    if data.get("purpose") != purpose:
        raise HTTPException(status_code=400, detail="Invalid token purpose")
    return data



security = HTTPBearer()
settings = get_settings()


def _device_fingerprint(request: Request, body_value: str | None) -> str:
    return (
        request.headers.get("X-Device-Fingerprint")
        or body_value
        or ""
    ).strip()


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
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
        credits_balance=0,
        credits_total_earned=0,
        max_concurrent_tasks=free_plan.max_concurrent_tasks if free_plan else 1,
        watermark_enabled=free_plan.watermark if free_plan else True,
    )
    db.add(profile)

    claim = await device_reputation.claim_signup_bonus(
        db,
        user,
        _device_fingerprint(request, user_data.device_fingerprint),
        ip=device_reputation.client_ip(request),
        user_agent=device_reputation.client_user_agent(request),
    )

    await db.commit()

    # Email sambutan + link verifikasi (gagal kirim tidak menggagalkan daftar).
    try:
        from app.core.config import get_settings

        verify_token = _sign_token("verify_email", 60 * 24, user_id=str(user.id))
        frontend = (get_settings().FRONTEND_URL or "https://proxyai.live").rstrip("/")
        await mailer.send(
            db,
            [user.email],
            "welcome",
            {
                "name": user.name or user.email.split("@")[0],
                "verify_url": f"{frontend}/verify-email?token={verify_token}",
            },
        )
    except Exception:  # noqa: BLE001
        pass

    # Generate tokens
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        signup_bonus_granted=bool(claim.get("granted")),
        credits_granted=int(claim.get("amount") or 0),
        device_status=claim.get("status"),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(User).where(User.email == login_data.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is deactivated")

    # Update last login
    user.last_login_at = __import__("datetime").datetime.utcnow()
    await device_reputation.associate_login(
        db,
        user,
        _device_fingerprint(request, login_data.device_fingerprint),
        ip=device_reputation.client_ip(request),
        user_agent=device_reputation.client_user_agent(request),
    )
    await db.commit()

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    refresh_value = (body.refresh_token or "").strip() or request.cookies.get(REFRESH_COOKIE, "")
    payload = decode_token(refresh_value)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    # Sesi yang sudah dicabut tidak boleh menghasilkan access token baru.
    from app.services.auth_session import is_token_revoked

    if await is_token_revoked(db, user.id, payload):
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")

    access_token = create_access_token({"sub": str(user.id)})
    new_refresh_token = create_refresh_token({"sub": str(user.id)})
    set_auth_cookies(
        response,
        access_token,
        new_refresh_token,
        csrf_token=request.cookies.get(CSRF_COOKIE),
    )
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


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
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db_session)):
    """Kirim link reset password (tidak membocorkan apakah email terdaftar)."""
    from app.core.config import get_settings

    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if user is not None:
        token = _sign_token("reset_password", 30, user_id=str(user.id))
        frontend = (get_settings().FRONTEND_URL or "https://proxyai.live").rstrip("/")
        await mailer.send(
            db,
            [user.email],
            "reset",
            {
                "name": user.name or user.email.split("@")[0],
                "reset_url": f"{frontend}/reset-password?token={token}",
            },
        )
    return {"message": "If email exists, reset link has been sent"}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db_session)):
    data = _read_token(request.token, "reset_password")
    user = await db.get(User, data.get("user_id"))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.password_hash = hash_password(request.new_password)
    await db.commit()
    return {"message": "Password has been reset"}


class VerifyEmailIn(BaseModel):
    token: str


@router.post("/verify-email")
async def verify_email(payload: VerifyEmailIn, db: AsyncSession = Depends(get_db_session)):
    data = _read_token(payload.token, "verify_email")
    user = await db.get(User, data.get("user_id"))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.email_verified = True
    await db.commit()
    return {"ok": True, "email": user.email}


class OtpRequestIn(BaseModel):
    email: str


class OtpVerifyIn(BaseModel):
    token: str
    code: str


@router.post("/request-otp")
async def request_otp(payload: OtpRequestIn, db: AsyncSession = Depends(get_db_session)):
    """Kirim kode OTP 6 digit ke email (berlaku 10 menit)."""
    import hashlib
    import secrets

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None:
        return {"ok": True, "message": "If the email exists, a code has been sent"}
    code = f"{secrets.randbelow(1_000_000):06d}"
    token = _sign_token(
        "email_otp",
        10,
        user_id=str(user.id),
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
    )
    await mailer.send(
        db,
        [user.email],
        "otp",
        {"name": user.name or "there", "code": code, "minutes": 10},
    )
    return {"ok": True, "token": token, "expires_in": 600}


@router.post("/verify-otp")
async def verify_otp(payload: OtpVerifyIn, db: AsyncSession = Depends(get_db_session)):
    import hashlib

    data = _read_token(payload.token, "email_otp")
    expected = str(data.get("code_hash") or "")
    actual = hashlib.sha256(str(payload.code).strip().encode()).hexdigest()
    if not expected or actual != expected:
        raise HTTPException(status_code=401, detail="Invalid OTP code")
    user = await db.get(User, data.get("user_id"))
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.email_verified = True
    await db.commit()
    return {"ok": True, "email": user.email}


GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


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
    db: AsyncSession,
    *,
    email: str,
    name: str,
    provider: AuthProvider,
    provider_id: str | None,
    avatar_url: str | None,
    request: Request,
    fingerprint: str,
) -> tuple[User, dict]:
    """Buat user baru dari OAuth; bonus mengikuti aturan device."""
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
            credits_balance=0,
            credits_total_earned=0,
            max_concurrent_tasks=free_plan.max_concurrent_tasks if free_plan else 1,
            watermark_enabled=free_plan.watermark if free_plan else True,
        )
    )
    claim = await device_reputation.claim_signup_bonus(
        db,
        user,
        fingerprint,
        ip=device_reputation.client_ip(request),
        user_agent=device_reputation.client_user_agent(request),
    )
    await db.commit()
    return user, claim


@router.get("/social-providers")
async def social_providers():
    """
    Provider OAuth yang siap dipakai (client id/secret tersedia di server).

    Frontend memakai endpoint ini untuk memutuskan tombol mana yang aktif,
    sehingga tombol tidak pernah "diam" tanpa penjelasan.
    """
    return {
        "google": bool(settings.GOOGLE_CLIENT_ID),
        "x": bool(settings.X_CLIENT_ID and settings.X_CLIENT_SECRET),
        "facebook": bool(settings.FACEBOOK_CLIENT_ID and settings.FACEBOOK_CLIENT_SECRET),
    }


@router.post("/social-login", response_model=TokenResponse)

async def social_login(
    data: SocialLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
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

    claim: dict = {}
    if user is None:
        user, claim = await _create_oauth_user(
            db,
            email=email,
            name=name,
            provider=auth_provider,
            provider_id=provider_id,
            avatar_url=avatar_url,
            request=request,
            fingerprint=_device_fingerprint(request, data.device_fingerprint),
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
        await device_reputation.associate_login(
            db,
            user,
            _device_fingerprint(request, data.device_fingerprint),
            ip=device_reputation.client_ip(request),
            user_agent=device_reputation.client_user_agent(request),
        )
        await db.commit()

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        signup_bonus_granted=bool(claim.get("granted")),
        credits_granted=int(claim.get("amount") or 0),
        device_status=claim.get("status"),
    )
