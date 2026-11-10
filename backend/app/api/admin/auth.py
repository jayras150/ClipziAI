"""
Admin authentication: login (lockout + TOTP), cookie HttpOnly, enrol TOTP.

Kenapa cookie: token admin tidak disimpan di localStorage (aman dari XSS).
Aplikasi admin memanggil /api/admin/* dari origin yang sama sehingga cookie
ikut otomatis. Header Authorization tetap didukung untuk script/CLI.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import ADMIN_COOKIE, get_current_admin
from app.api.deps import get_db_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.admin_user import AdminRole, AdminUser
from app.schemas.auth import TokenResponse

router = APIRouter()

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
ACCESS_MINUTES = 15


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class TotpCodeRequest(BaseModel):
    code: str


class AdminMeResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    two_factor_enabled: bool


def _set_auth_cookie(response: Response, token: str) -> None:
    """Cookie HttpOnly: JS tidak bisa membaca token admin."""
    response.set_cookie(
        key=ADMIN_COOKIE,
        value=token,
        max_age=ACCESS_MINUTES * 60,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_admin_by_email(db: AsyncSession, email: str) -> Optional[AdminUser]:
    result = await db.execute(select(AdminUser).where(AdminUser.email == email.lower()))
    return result.scalar_one_or_none()


@router.post("/login", response_model=TokenResponse)
async def admin_login(
    login_data: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
):
    admin = await _get_admin_by_email(db, login_data.email)

    if not admin or not admin.password_hash:
        raise HTTPException(status_code=401, detail="Email atau password salah")

    # Lockout: mencegah brute force walau password lemah.
    if admin.lock_until and admin.lock_until > _now():
        sisa = int((admin.lock_until - _now()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Akun terkunci. Coba lagi dalam {sisa} menit.",
        )

    if not admin.is_active:
        raise HTTPException(status_code=401, detail="Akun admin tidak aktif")

    if not verify_password(login_data.password, admin.password_hash):
        admin.failed_login_attempts = (admin.failed_login_attempts or 0) + 1
        if admin.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            admin.lock_until = _now() + timedelta(minutes=LOCK_MINUTES)
            admin.failed_login_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Terlalu banyak percobaan. Akun dikunci {LOCK_MINUTES} menit.",
            )
        await db.commit()
        raise HTTPException(status_code=401, detail="Email atau password salah")

    if admin.two_factor_enabled:
        code = (login_data.totp_code or "").strip()
        if not code or not admin.two_factor_secret:
            raise HTTPException(status_code=401, detail="Kode TOTP wajib diisi")
        if not pyotp.TOTP(admin.two_factor_secret).verify(code, valid_window=1):
            raise HTTPException(status_code=401, detail="Kode TOTP salah")

    admin.failed_login_attempts = 0
    admin.lock_until = None
    admin.last_login_at = _now()
    admin.last_login_ip = request.client.host if request.client else None
    await db.commit()

    access_token = create_access_token(
        {"sub": str(admin.id), "role": admin.role.value}, timedelta(minutes=ACCESS_MINUTES)
    )
    refresh_token = create_refresh_token({"sub": str(admin.id), "role": admin.role.value})
    _set_auth_cookie(response, access_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"message": "Logged out"}


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(current_admin: AdminUser = Depends(get_current_admin)):
    return AdminMeResponse(
        id=str(current_admin.id),
        email=current_admin.email,
        name=current_admin.name,
        role=current_admin.role.value,
        two_factor_enabled=bool(current_admin.two_factor_enabled),
    )


@router.post("/totp/setup")
async def totp_setup(
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Buat secret baru. 2FA belum aktif sampai kode diverifikasi di /totp/enable."""
    secret = pyotp.random_base32()
    current_admin.two_factor_secret = secret
    current_admin.two_factor_enabled = False
    await db.commit()
    return {
        "secret": secret,
        "otpauth_url": pyotp.TOTP(secret).provisioning_uri(
            name=current_admin.email, issuer_name="ClipzyAI Admin"
        ),
    }


@router.post("/totp/enable")
async def totp_enable(
    payload: TotpCodeRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    if not current_admin.two_factor_secret:
        raise HTTPException(status_code=400, detail="Jalankan /totp/setup dulu")
    if not pyotp.TOTP(current_admin.two_factor_secret).verify(
        payload.code.strip(), valid_window=1
    ):
        raise HTTPException(status_code=400, detail="Kode TOTP salah")
    current_admin.two_factor_enabled = True
    await db.commit()
    return {"two_factor_enabled": True}


@router.post("/totp/disable")
async def totp_disable(
    payload: TotpCodeRequest,
    current_admin: AdminUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    if current_admin.two_factor_enabled:
        if not current_admin.two_factor_secret or not pyotp.TOTP(
            current_admin.two_factor_secret
        ).verify(payload.code.strip(), valid_window=1):
            raise HTTPException(status_code=400, detail="Kode TOTP salah")
    current_admin.two_factor_enabled = False
    current_admin.two_factor_secret = None
    await db.commit()
    return {"two_factor_enabled": False}


@router.post("/bootstrap", status_code=201)
async def bootstrap_admin(
    payload: AdminLoginRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Buat admin pertama HANYA jika tabel admin masih kosong.
    Setelah ada satu admin, endpoint ini selalu 403 (selanjutnya lewat script).
    """
    existing = (await db.execute(select(AdminUser))).scalars().first()
    if existing:
        raise HTTPException(
            status_code=403, detail="Admin sudah ada; gunakan script create_admin"
        )
    admin = AdminUser(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name="Owner",
        role=AdminRole.SUPER_ADMIN,
        is_active=True,
        can_adjust_credits=True,
        can_ban_users=True,
        can_manage_plans=True,
        can_view_audit=True,
    )
    db.add(admin)
    await db.commit()
    return {"id": str(admin.id), "email": admin.email}
