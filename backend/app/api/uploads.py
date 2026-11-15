"""
Direct-to-storage upload endpoints.

Browser mengunggah file video langsung ke R2/S3 memakai presigned PUT, sehingga
byte video tidak melewati API VPS. API hanya menerbitkan URL sementara setelah
memvalidasi tipe file, ukuran, dan (bila dikirim) durasi.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models.user import User
from app.services.storage_registry import get_storage

router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 6 * 60 * 60
ALLOWED_VIDEO_TYPES = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-msvideo": "avi",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
}


def validate_upload_request(
    *,
    filename: str,
    content_type: str,
    size: int,
    duration_seconds: Optional[float] = None,
) -> str:
    """Validasi input presign dan kembalikan ekstensi yang aman.

    Dipisah dari endpoint agar bisa diuji tanpa storage/network.
    """
    clean_type = (content_type or "").split(";")[0].strip().lower()
    if clean_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only MP4, MOV, AVI, WEBM, or MKV video files are supported.",
        )
    if not filename or not str(filename).strip():
        raise HTTPException(status_code=400, detail="A file name is required.")
    if size <= 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Video is too large. Maximum size is 2 GB.",
        )
    if duration_seconds is not None:
        duration = float(duration_seconds)
        if duration < MIN_DURATION_SECONDS:
            raise HTTPException(status_code=400, detail="Video duration is too short.")
        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(
                status_code=400,
                detail="Video is too long. Maximum duration is 6 hours.",
            )

    # Jangan percaya nama file mentah: hanya ekstensi yang dikenal yang masuk key.
    suffix = str(filename).rsplit(".", 1)[-1].lower() if "." in str(filename) else ""
    if suffix not in set(ALLOWED_VIDEO_TYPES.values()):
        suffix = ALLOWED_VIDEO_TYPES[clean_type]
    if not re.fullmatch(r"[a-z0-9]{2,5}", suffix):
        suffix = ALLOWED_VIDEO_TYPES[clean_type]
    return suffix


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=3, max_length=100)
    size: int = Field(gt=0)
    duration_seconds: Optional[float] = Field(default=None, ge=0)


class PresignUploadResponse(BaseModel):
    upload_url: str
    public_url: str
    object_key: str
    expires_in: int
    max_bytes: int


@router.post("/presign", response_model=PresignUploadResponse)
async def presign_upload(
    payload: PresignUploadRequest,
    current_user: User = Depends(get_current_user),
) -> PresignUploadResponse:
    """Terbitkan URL PUT sementara untuk upload video langsung ke storage."""
    suffix = validate_upload_request(
        filename=payload.filename,
        content_type=payload.content_type,
        size=payload.size,
        duration_seconds=payload.duration_seconds,
    )
    clean_type = payload.content_type.split(";")[0].strip().lower()
    storage = get_storage()
    key = storage.generate_object_key(
        str(current_user.id),
        f"source.{suffix}",
        folder=f"uploads/{current_user.id}",
    )
    upload_url = storage.presign_put(key, clean_type, expiration=3600)
    if not upload_url:
        raise HTTPException(
            status_code=503,
            detail=(
                "Storage is not configured, so direct upload is unavailable. "
                "Ask an administrator to configure Settings > Storage."
            ),
        )
    public_url = storage.get_public_url(key)
    if not public_url:
        raise HTTPException(
            status_code=503,
            detail="Storage did not return a public object URL.",
        )
    return PresignUploadResponse(
        upload_url=upload_url,
        public_url=public_url,
        object_key=key,
        expires_in=3600,
        max_bytes=MAX_UPLOAD_BYTES,
    )
