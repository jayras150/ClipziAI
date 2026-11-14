"""Endpoint admin untuk branding: nama app, logo, favicon, warna."""
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services.branding import DEFAULT_BRANDING, get_branding, normalize_branding, set_branding
from app.services.storage_registry import get_storage

router = APIRouter()

ALLOWED_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
}
MAX_BYTES = 2 * 1024 * 1024

# Video animasi landing page (hero) — mp4/webm, maksimum 30 MB.
VIDEO_TYPES = {
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}
MAX_VIDEO_BYTES = 30 * 1024 * 1024


def _image_size(data: bytes) -> tuple[Optional[int], Optional[int]]:
    """Dimensi gambar (untuk card preview di dashboard). SVG/ICO bisa gagal."""
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return image.width, image.height
    except Exception:
        return None, None


class BrandingIn(BaseModel):
    app_name: str = Field(default="Clipzy AI", max_length=60)
    tagline: Optional[str] = Field(default=None, max_length=120)
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    og_image_url: Optional[str] = None
    hero_video_url: Optional[str] = None
    accent_color: str = "#f4c76b"
    support_email: Optional[str] = Field(default=None, max_length=120)
    footer_note: Optional[str] = Field(default=None, max_length=160)


@router.get("/branding")
async def read_branding(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    return await get_branding(db)


@router.put("/branding")
async def update_branding(
    payload: BrandingIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    before = await get_branding(db)
    after = await set_branding(db, payload.model_dump())
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_branding_updated",
            resource_type="platform_setting",
            resource_id="branding",
            old_values=before,
            new_values=after,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return after


@router.post("/branding/upload")
async def upload_branding_asset(
    request: Request,
    kind: str,
    file: UploadFile = File(...),
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Unggah logo/favicon/og image (atau video hero landing) ke storage."""
    if kind not in {"logo", "favicon", "og", "hero"}:
        raise HTTPException(status_code=400, detail="kind harus logo, favicon, og, atau hero")

    content_type = (file.content_type or "").lower().split(";")[0].strip()

    if kind == "hero":
        extension = VIDEO_TYPES.get(content_type)
        if not extension:
            raise HTTPException(status_code=400, detail="Video harus MP4, WEBM, atau MOV.")
        limit = MAX_VIDEO_BYTES
        field = "hero_video_url"
    else:
        extension = ALLOWED_TYPES.get(content_type)
        if not extension:
            raise HTTPException(
                status_code=400, detail="Format harus PNG, JPEG, WEBP, SVG, atau ICO."
            )
        limit = MAX_BYTES
        field = "logo_url" if kind == "logo" else "favicon_url" if kind == "favicon" else "og_image_url"

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="File kosong.")
    if len(data) > limit:
        raise HTTPException(
            status_code=400,
            detail="Ukuran maksimum %d MB." % (limit // (1024 * 1024)),
        )

    key = "branding/%s/%s.%s" % (kind, uuid4().hex, extension)
    try:
        storage = get_storage()
        url = storage.upload_bytes(
            data,
            key,
            content_type,
            # Nama objek selalu unik (uuid) sehingga aman di-cache lama.
            cache_control="public, max-age=31536000, immutable",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Gagal unggah ke storage: %s" % str(exc)[:200])

    width, height = _image_size(data) if kind != "hero" else (None, None)

    before = await get_branding(db)
    payload = dict(before)
    payload[field] = url
    after = await set_branding(db, payload)

    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_branding_asset_uploaded",
            resource_type="platform_setting",
            resource_id="branding",
            old_values=before,
            new_values=after,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    # Kembalikan detail aset supaya dashboard bisa menampilkan card preview
    # (dimensi & ukuran) tanpa mengunduh ulang gambar.
    return {
        "kind": kind,
        "url": url,
        "size_bytes": len(data),
        "content_type": content_type,
        "width": width,
        "height": height,
        "branding": after,
    }


@router.post("/branding/reset")
async def reset_branding(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    return await set_branding(db, normalize_branding(None))
