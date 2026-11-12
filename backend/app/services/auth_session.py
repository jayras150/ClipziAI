"""
Pencabutan sesi (revocation) untuk JWT.

Dipakai oleh:
  - `POST /api/admin/auth/logout-all`   (admin mengeluarkan semua sesinya)
  - `POST /api/admin/users/{id}/force-logout` (admin mengeluarkan sesi user)
  - `get_current_user()`                 (menolak token yang sudah dicabut)

Kenapa pakai `revoked_before` + `iat`, bukan daftar token: token JWT tidak
disimpan di server, jadi cara termurah & bebas migrasi adalah membandingkan
waktu terbit token dengan waktu pencabutan terakhir user.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_revocation import AuthRevocation


def _as_aware(value: datetime) -> datetime:
    """Normalisasi datetime dari DB (bisa naive) supaya bisa dibandingkan."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def get_revocation(db: AsyncSession, user_id: UUID) -> Optional[AuthRevocation]:
    result = await db.execute(select(AuthRevocation).where(AuthRevocation.user_id == user_id))
    return result.scalar_one_or_none()


async def revoke_sessions(
    db: AsyncSession, user_id: UUID, reason: Optional[str] = None
) -> datetime:
    """Cabut semua token user yang terbit sebelum `now`. Return waktu cabut."""
    now = datetime.now(timezone.utc)
    row = await get_revocation(db, user_id)
    if row is None:
        row = AuthRevocation(user_id=user_id, revoked_before=now, reason=reason)
        db.add(row)
    else:
        row.revoked_before = now
        row.reason = reason
    await db.commit()
    return now


async def is_token_revoked(db: AsyncSession, user_id: UUID, payload: dict) -> bool:
    """
    True bila token harus ditolak.

    Aturan: bila user punya baris revocation, token yang `iat`-nya hilang
    (token lama sebelum fitur ini) atau lebih lama dari `revoked_before`
    dianggap tidak berlaku.
    """
    row = await get_revocation(db, user_id)
    if row is None:
        return False

    revoked_before = _as_aware(row.revoked_before)
    issued_at = payload.get("iat")
    if issued_at is None:
        return True

    try:
        if isinstance(issued_at, (int, float)):
            issued = datetime.fromtimestamp(float(issued_at), tz=timezone.utc)
        else:
            issued = datetime.fromisoformat(str(issued_at).replace("Z", "+00:00"))
            issued = _as_aware(issued)
    except (TypeError, ValueError):
        return True

    return issued < revoked_before


async def clear_revocation(db: AsyncSession, user_id: UUID) -> bool:
    """Hapus pencabutan (mis. setelah user mengganti password baru)."""
    row = await get_revocation(db, user_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
