"""
Info akun untuk dashboard admin + logout.

Login memakai endpoint user biasa (`POST /api/auth/login`) — tidak ada login
admin terpisah lagi. Hak admin ditentukan oleh `ADMIN_EMAILS` di environment
dan diperiksa di server lewat `get_current_admin`.

Logout: JWT bersifat stateless, jadi "keluar" = klien membuang cookie. Endpoint
di bawah mencatat kejadiannya ke audit log dan (untuk `logout-all`) mencabut
semua token yang beredar lewat tabel `auth_revocations`.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import admin_emails, get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services.auth_session import get_revocation, revoke_sessions

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


async def _audit(
    db: AsyncSession,
    request: Request,
    current_admin: User,
    action: str,
    meta: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action=action,
            resource_type="session",
            resource_id=str(current_admin.id),
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


@router.post("/logout")
async def admin_logout(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Catat logout. Klien menghapus cookie sesi di sisi browser."""
    await _audit(db, request, current_admin, "admin_logout")
    return {"message": "Logout tercatat."}


@router.post("/logout-all")
async def admin_logout_all(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Cabut SEMUA token milik akun admin ini (semua perangkat/browser).

    Dipakai juga sebagai tombol "keluar dari semua perangkat" dan menjadi
    contoh untuk `force-logout` user di halaman Users.
    """
    revoked_before = await revoke_sessions(
        db, current_admin.id, reason="admin_logout_all"
    )
    await _audit(
        db,
        request,
        current_admin,
        "admin_logout_all",
        {"revoked_before": revoked_before.isoformat()},
    )
    return {
        "message": "Semua sesi dicabut. Silakan login lagi.",
        "revoked_before": revoked_before.isoformat(),
    }


@router.get("/session")
async def admin_session(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Ringkasan sesi: kapan pencabutan terakhir dilakukan (kalau ada)."""
    revocation = await get_revocation(db, current_admin.id)
    return {
        "user_id": str(current_admin.id),
        "email": current_admin.email,
        "revoked_before": revocation.revoked_before.isoformat()
        if revocation and revocation.revoked_before
        else None,
        "revocation_reason": revocation.reason if revocation else None,
    }

