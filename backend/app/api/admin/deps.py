"""
Akses admin berbasis email (tanpa akun admin terpisah).

User yang login normal otomatis jadi admin kalau emailnya terdaftar di
environment `ADMIN_EMAILS` (dipisah koma). Semua endpoint admin memanggil
dependency ini di server, jadi UI tidak bisa "dipaksa" membuka akses.

Kenapa begini: menghindari login admin kedua, TOTP terpisah, subdomain, dan IP
allowlist. Satu sistem login (user) + daftar email di env.
"""
from typing import Optional

from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.user import User

settings = get_settings()


def admin_emails() -> set[str]:
    """Daftar email admin dari env (`ADMIN_EMAILS=a@x.com,b@y.com`)."""
    raw = getattr(settings, "ADMIN_EMAILS", "") or ""
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_admin_email(email: Optional[str]) -> bool:
    if not email:
        return False
    return email.strip().lower() in admin_emails()


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency admin: user login biasa + emailnya ada di allowlist."""
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Akun tidak aktif")
    if not is_admin_email(user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini tidak punya akses admin",
        )
    return user


# Alias supaya pemanggilan lama (`require_admin`) tetap jalan.
require_admin = get_current_admin

__all__ = ["admin_emails", "is_admin_email", "get_current_admin", "require_admin"]
