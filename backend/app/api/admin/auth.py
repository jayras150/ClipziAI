"""
Info akun untuk dashboard admin.

Login memakai endpoint user biasa (`POST /api/auth/login`) — tidak ada login
admin terpisah lagi. Hak admin ditentukan oleh `ADMIN_EMAILS` di environment
dan diperiksa di server lewat `get_current_admin`.
"""
from fastapi import APIRouter, Depends

from app.api.admin.deps import admin_emails, get_current_admin
from app.models.user import User

router = APIRouter()


@router.get("/me")
async def admin_me(current_admin: User = Depends(get_current_admin)):
    return {
        "id": str(current_admin.id),
        "email": current_admin.email,
        "name": current_admin.name,
        "is_admin": True,
        "admin_emails": sorted(admin_emails()),
    }
