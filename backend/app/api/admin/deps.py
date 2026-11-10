"""
Dependency autentikasi admin.

Admin punya tabel sendiri (`admin_users`), jadi token user biasa TIDAK boleh
dipakai. Token admin dibuat oleh `create_access_token` dengan claim `role`,
dan di sini claim itu wajib ada.
"""
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.security import decode_token
from app.models.admin_user import AdminUser

ADMIN_COOKIE = "clipzi_admin"
admin_security = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials]
) -> Optional[str]:
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(ADMIN_COOKIE)


async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(admin_security),
    db: AsyncSession = Depends(get_db_session),
) -> AdminUser:
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )

    payload = decode_token(token)
    if not payload or payload.get("type") != "access" or not payload.get("role"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token",
        )

    admin_id = payload.get("sub")
    try:
        admin = await db.get(AdminUser, UUID(str(admin_id)))
    except (ValueError, AttributeError, TypeError):
        admin = None

    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account not found or inactive",
        )
    return admin


__all__ = ["ADMIN_COOKIE", "get_current_admin"]
