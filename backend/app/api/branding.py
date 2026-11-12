"""Endpoint publik: branding yang dipakai frontend (logo, favicon, nama)."""
import hashlib

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.branding import get_branding

router = APIRouter()


@router.get("/branding")
async def public_branding(response: Response, db: AsyncSession = Depends(get_db_session)):
    """
    Branding untuk frontend (layout, navbar, footer, header dashboard).

    `Cache-Control: no-store` supaya perubahan dari admin langsung terlihat di
    semua tab; `version` dipakai untuk cache-busting favicon/logo di metadata.
    """
    branding = await get_branding(db)
    fingerprint = "|".join(
        str(branding.get(key) or "")
        for key in ("app_name", "logo_url", "favicon_url", "og_image_url", "accent_color")
    )
    version = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:10]

    response.headers["Cache-Control"] = "no-store, max-age=0"
    return {**branding, "version": version}

