"""
Admin API - manajemen & rotasi cookies yt-dlp.

Alur rotasi:
  1. Cookies yang valid disimpan sebagai baris di tabel ytdlp_cookies
     (terenkripsi AES-256-GCM, bukan di .env).
  2. `acquire()` memilih cookies aktif yang paling lama tidak dipakai
     (round-robin) dan menulisnya ke file cache writable.
  3. yt-dlp menulis balik token yang di-refresh YouTube ke file itu.
  4. `sync_back()` mengenkripsi ulang isinya ke database -> token tetap segar
     tanpa intervensi manual.
  5. Bila sesi Google benar-benar mati, cookies ditandai `expired`
     (otomatis lewat probe/cron atau manual), lalu cookies baru di-upload
     ke endpoint ini.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.security import decrypt_field
from app.models.ytdlp_cookie import YtdlpCookie
from app.services import cookie_store

logger = logging.getLogger(__name__)

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


class CookieCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120, description="Nama unik, mis. 'akun-1'")
    cookies: str = Field(min_length=10, description="Isi cookies.txt (format Netscape)")


class CookieItem(BaseModel):
    id: UUID
    label: str
    status: str
    fail_count: int
    success_count: int
    refreshed_by_ytdlp: bool
    last_used_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_error: Optional[str] = None


def _to_item(cookie: YtdlpCookie) -> CookieItem:
    return CookieItem(
        id=cookie.id,
        label=cookie.label,
        status=cookie.status,
        fail_count=cookie.fail_count,
        success_count=cookie.success_count,
        refreshed_by_ytdlp=cookie.refreshed_by_ytdlp,
        last_used_at=cookie.last_used_at.isoformat() if cookie.last_used_at else None,
        last_checked_at=cookie.last_checked_at.isoformat() if cookie.last_checked_at else None,
        last_error=cookie.last_error,
    )


async def _get_or_404(db: AsyncSession, cookie_id: UUID) -> YtdlpCookie:
    cookie = await db.get(YtdlpCookie, cookie_id)
    if not cookie:
        raise HTTPException(status_code=404, detail="Cookies tidak ditemukan.")
    return cookie


@router.get("", response_model=list[CookieItem])
async def list_cookies(db: AsyncSession = Depends(get_db_session)):
    """Daftar semua cookies (tanpa isi/ciphertext)."""
    return [_to_item(c) for c in await cookie_store.list_cookies(db)]


@router.post("", response_model=CookieItem, status_code=201)
async def create_cookie(
    payload: CookieCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Upload cookies.txt baru (menimpa label yang sama)."""
    try:
        cookie = await cookie_store.add_cookie(db, payload.label, payload.cookies)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_item(cookie)


@router.post("/probe-all")
async def probe_all(db: AsyncSession = Depends(get_db_session)):
    """Uji semua cookies aktif, rotasi otomatis bila ada yang expired."""
    return {"results": await cookie_store.probe_all(db)}


@router.post("/{cookie_id}/probe")
async def probe_one(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    cookie = await _get_or_404(db, cookie_id)
    ok, error = await cookie_store.probe(db, cookie)
    return {"ok": ok, "status": cookie.status, "error": error}


@router.post("/{cookie_id}/reactivate", response_model=CookieItem)
async def reactivate(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    cookie = await _get_or_404(db, cookie_id)
    await cookie_store.reactivate(db, cookie)
    return _to_item(cookie)


@router.post("/{cookie_id}/disable", response_model=CookieItem)
async def disable(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    cookie = await _get_or_404(db, cookie_id)
    await cookie_store.mark_disabled(db, cookie)
    return _to_item(cookie)


@router.get("/{cookie_id}/content")
async def reveal_content(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """Tampilkan isi cookies (plaintext) - untuk verifikasi admin.

    Hanya untuk debugging. Jangan pernah dipanggil dari frontend publik.
    """
    cookie = await _get_or_404(db, cookie_id)
    try:
        return {"label": cookie.label, "cookies": decrypt_field(cookie.encrypted_cookies)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal dekripsi: {exc}") from exc


@router.delete("/{cookie_id}", status_code=204)
async def delete(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    if not await cookie_store.delete_cookie(db, cookie_id):
        raise HTTPException(status_code=404, detail="Cookies tidak ditemukan.")
    return None
