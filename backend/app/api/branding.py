"""Endpoint publik: branding yang dipakai frontend (logo, favicon, nama)."""
import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.branding import get_branding
from app.services.storage_registry import get_storage

router = APIRouter()

# Key objek aset branding: branding/<kind>/<uuid>.<ext> (favicon punya slot).
_ASSET_KEY = re.compile(r"^branding/[A-Za-z0-9._/-]+$")


@router.get("/branding/asset/{key:path}")
async def public_branding_asset(key: str):
    """URL permanen untuk aset branding (logo, favicon, OG image, video hero).

    Storage S3/R2 mengembalikan URL presigned yang kedaluwarsa (maksimal 7
    hari), jadi URL itu TIDAK boleh disimpan sebagai branding: setelah seminggu
    logo/favicon/video hero akan 404. Endpoint ini menyimpan *key* objek dan
    mengalihkan (307) ke presigned URL baru setiap permintaan.
    """
    if not _ASSET_KEY.fullmatch(key) or ".." in key:
        raise HTTPException(status_code=404, detail="Aset tidak ditemukan")
    try:
        storage = get_storage()
        target = storage.get_presigned_url(key, expiration=6 * 3600)
    except Exception as exc:  # noqa: BLE001 - storage belum dikonfigurasi
        raise HTTPException(status_code=404, detail="Aset tidak ditemukan") from exc
    if not target:
        raise HTTPException(status_code=404, detail="Aset tidak ditemukan")
    # Browser boleh cache redirect sebentar; presigned URL sendiri berumur 6 jam.
    return RedirectResponse(
        target, status_code=307, headers={"Cache-Control": "public, max-age=1800"}
    )


@router.get("/branding")
async def public_branding(response: Response, db: AsyncSession = Depends(get_db_session)):
    """
    Branding untuk frontend (layout, navbar, footer, header dashboard).

    `Cache-Control: no-store` supaya perubahan dari admin langsung terlihat di
    semua tab; `version` dipakai untuk cache-busting favicon/logo di metadata.
    """
    branding = await get_branding(db)
    favicons = branding.get("favicons") if isinstance(branding.get("favicons"), dict) else {}
    fingerprint = "|".join(
        str(branding.get(key) or "")
        for key in ("app_name", "logo_url", "favicon_url", "og_image_url", "accent_color")
    ) + "|" + "|".join(f"{slot}={favicons.get(slot) or ''}" for slot in sorted(favicons))
    version = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:10]

    response.headers["Cache-Control"] = "no-store, max-age=0"
    return {**branding, "version": version}

