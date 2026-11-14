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
import base64
import binascii
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.security import decrypt_field, encrypt_field
from app.models.ytdlp_cookie import YtdlpCookie
from app.services import cookie_store

logger = logging.getLogger(__name__)

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


class CookieCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120, description="Nama unik, mis. 'akun-1'")
    cookies: Optional[str] = Field(
        default=None, description="Isi cookies.txt (format Netscape)"
    )
    cookies_base64: Optional[str] = Field(
        default=None, description="Alternatif: isi cookies.txt yang di-encode base64"
    )
    store_base64: bool = Field(
        default=True,
        description="Simpan juga base64 terenkripsi untuk ENV worker (fallback)",
    )


def decode_cookies_base64(value: str) -> str:
    """
    Ubah base64 -> teks cookies.txt dengan toleransi:
      - prefix `data:text/plain;base64,`
      - spasi/baris baru sisa copy-paste
      - varian urlsafe (- dan _)
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("Isi base64 kosong.")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    text = "".join(text.split())
    text = text.replace("-", "+").replace("_", "/")
    padding = len(text) % 4
    if padding:
        text += "=" * (4 - padding)
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Base64 tidak valid. Pastikan menyalin seluruh isi file.") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Hasil decode bukan teks UTF-8 (bukan cookies.txt).") from exc


def encode_cookies_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def summarize_cookies(text: str) -> dict:
    """Ringkasan aman (tanpa membocorkan value) untuk ditampilkan di UI."""
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    domains = set()
    expires = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domains.add(parts[0].lstrip("."))
        try:
            stamp = int(parts[4])
            if stamp > 0:
                expires.append(stamp)
        except ValueError:
            continue
    fastest = None
    if expires:
        from datetime import datetime, timezone

        fastest = datetime.fromtimestamp(min(expires), tz=timezone.utc).isoformat()
    return {
        "cookie_count": len(lines),
        "domains": sorted(domains)[:10],
        "earliest_expiry": fastest,
        "bytes": len(text.encode("utf-8")),
    }



async def _save_global_base64(
    db: AsyncSession, label: str, plain: str, *, mode: Optional[str] = None
) -> str:
    """Simpan base64 terenkripsi di platform_settings + inject ke ENV runtime.

    Ini adalah base64 global (satu yang aktif) untuk fallback worker ketika pool
    DB kosong. Nilai per akun tetap bisa diambil kapan saja lewat endpoint
    `GET /{id}/base64` (tidak disimpan duplikat di baris cookie).
    """
    from datetime import datetime, timezone

    from app.core.config import get_settings
    from app.services import platform_settings as ps

    encoded = encode_cookies_base64(plain)
    stored = await ps.get_setting(db, "youtube", {}) or {}
    value = dict(stored) if isinstance(stored, dict) else {}
    value.update(
        {
            "mode": mode or value.get("mode") or "db",
            "label": label,
            "cookies_base64_enc": encrypt_field(encoded),
            "summary": summarize_cookies(plain),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await ps.set_setting(db, "youtube", value)
    get_settings().YTDLP_COOKIES_BASE64 = encoded
    return encoded


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
    base64_saved: bool = False


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
    """
    Upload cookies baru (menimpa label yang sama).

    Bisa mengirim `cookies` (format Netscape apa adanya) ATAU `cookies_base64`
    (hasil `base64 cookies.txt`) — base64 akan di-decode & divalidasi lebih dulu.
    """
    text = (payload.cookies or "").strip()
    if not text and payload.cookies_base64:
        try:
            text = decode_cookies_base64(payload.cookies_base64)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="Isi cookies wajib (Netscape atau base64).")

    try:
        cookie = await cookie_store.add_cookie(db, payload.label, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = _to_item(cookie)
    if payload.store_base64:
        await _save_global_base64(db, payload.label, text)
        item.base64_saved = True
    return item


@router.post("/validate")
async def validate_input(payload: CookieCreate):
    """
    Cek isi cookies sebelum disimpan: deteksi format, jumlah cookie, domain,
    dan kedaluwarsa tercepat. Tidak menyimpan apa pun.
    """
    raw = (payload.cookies or "").strip()
    source = "netscape"
    if not raw and payload.cookies_base64:
        try:
            raw = decode_cookies_base64(payload.cookies_base64)
        except ValueError as exc:
            return {"valid": False, "error": str(exc)}
        source = "base64"
    if not raw:
        return {"valid": False, "error": "Isi cookies kosong."}

    try:
        cookie_store.validate_cookies_text(raw)
    except ValueError as exc:
        return {"valid": False, "error": str(exc), "source": source}

    return {"valid": True, "source": source, "summary": summarize_cookies(raw)}


@router.post("/import-base64", response_model=CookieItem, status_code=201)
async def import_base64(
    payload: CookieCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Endpoint khusus base64 (dipakai form 'Tempel base64' di dashboard)."""
    if not payload.cookies_base64:
        raise HTTPException(status_code=400, detail="Field cookies_base64 wajib diisi.")
    try:
        text = decode_cookies_base64(payload.cookies_base64)
        cookie = await cookie_store.add_cookie(db, payload.label, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_item(cookie)


@router.post("/encode")
async def encode_cookie_text(payload: dict):
    """Encode cookies.txt (Netscape) → base64 TANPA menyimpan.

    Dipakai tombol "Encode → Base64" di admin. Base64 hanya dikembalikan ke
    admin; tidak ditulis ke log.
    """
    raw = str(payload.get("cookies") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Isi cookies kosong.")
    try:
        cookie_store.validate_cookies_text(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "valid": True,
        "base64": encode_cookies_base64(raw),
        "summary": summarize_cookies(raw),
    }


@router.get("/settings")
async def read_youtube_settings(db: AsyncSession = Depends(get_db_session)):
    """Mode cookies yang aktif: rotasi DB (disarankan) atau base64 env."""
    from app.services import platform_settings as ps

    raw = await ps.get_setting(db, "youtube", {}) or {}
    return {
        "mode": raw.get("mode") or "db",
        "label": raw.get("label"),
        "updated_at": raw.get("updated_at"),
        "base64_set": bool(raw.get("cookies_base64_enc")),
        "base64_chars": len(raw.get("cookies_base64_enc") or ""),
        "summary": raw.get("summary"),
    }


@router.put("/settings")
async def update_youtube_settings(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Simpan setelan cookies YouTube.

    body: {"mode": "db"|"base64", "label": "akun-1", "cookies_base64": "..."}

    Mode `base64` menyimpan base64 terenkripsi di platform_settings dan langsung
    meng-inject ke `settings.YTDLP_COOKIES_BASE64` (tanpa rebuild image).
    """
    from app.services import platform_settings as ps

    mode = str(payload.get("mode") or "db").lower()
    if mode not in ("db", "base64"):
        raise HTTPException(status_code=400, detail="Mode harus 'db' atau 'base64'.")

    label = str(payload.get("label") or "").strip() or "env-base64"
    base64_text = (payload.get("cookies_base64") or "").strip()
    stored = await ps.get_setting(db, "youtube", {}) or {}
    value = dict(stored) if isinstance(stored, dict) else {}
    value["mode"] = mode
    await ps.set_setting(db, "youtube", value)

    env_injected = False
    if base64_text:
        try:
            plain = decode_cookies_base64(base64_text)
            cookie_store.validate_cookies_text(plain)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Simpan sebagai baris rotasi DB (primary) + base64 global terenkripsi
        # untuk worker yang masih membaca ENV.
        await cookie_store.add_cookie(db, label, plain)
        await _save_global_base64(db, label, plain, mode=mode)
        env_injected = True

    fresh = await ps.get_setting(db, "youtube", {}) or {}
    return {
        "mode": fresh.get("mode") or mode,
        "label": fresh.get("label"),
        "base64_set": bool(fresh.get("cookies_base64_enc")),
        "updated_at": fresh.get("updated_at"),
        "summary": fresh.get("summary"),
        "env_injected": env_injected,
    }


@router.get("/{cookie_id}/base64")
async def export_base64(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """
    Ekspor cookies tersimpan sebagai base64 (untuk ditempel ke env worker
    seperti `YTDLP_COOKIES_BASE64`). Hanya admin.
    """
    cookie = await _get_or_404(db, cookie_id)
    try:
        plain = decrypt_field(cookie.encrypted_cookies)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal dekripsi: {exc}") from exc
    return {
        "label": cookie.label,
        "base64": encode_cookies_base64(plain),
        "summary": summarize_cookies(plain),
    }


@router.post("/{cookie_id}/base64/store")
async def store_base64_for_env(cookie_id: UUID, db: AsyncSession = Depends(get_db_session)):
    """Jadikan base64 akun ini sebagai base64 global untuk ENV worker."""
    cookie = await _get_or_404(db, cookie_id)
    try:
        plain = decrypt_field(cookie.encrypted_cookies)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gagal dekripsi: {exc}") from exc
    try:
        cookie_store.validate_cookies_text(plain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    encoded = await _save_global_base64(db, cookie.label, plain)
    return {
        "ok": True,
        "label": cookie.label,
        "base64_set": True,
        "base64_chars": len(encoded),
        "summary": summarize_cookies(plain),
    }


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
