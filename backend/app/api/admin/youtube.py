"""
Admin — unggah klip mana pun ke channel YouTube milik admin.

Dipakai untuk dukungan pelanggan & verifikasi konfigurasi YouTube: admin bisa
menguji unggahan memakai klip yang sudah dirender user lain, tanpa perlu login
sebagai user tersebut. Klip tetap diperbarui (`youtube_uploaded`,
`youtube_video_id`) dan setiap aksi dicatat di audit log.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.api.youtube import (
    YOUTUBE_UPLOAD_JOBS,
    _check_video_source,
    _run_youtube_upload,
)
from app.core.security import decrypt_field, encrypt_field
from app.models.audit_log import ActorType, AuditLog
from app.models.clip import Clip
from app.models.user import User
from app.models.youtube_credential import YouTubeCredential
from app.services.metadata_generator import MetadataGenerationError, MetadataGenerator
from app.services.youtube_service import YouTubeService

router = APIRouter()
youtube_service = YouTubeService()


class AdminYouTubeUploadIn(BaseModel):
    privacy_status: str = "unlisted"
    category_id: str = "22"
    force: bool = False


@router.post("/upload/{clip_id}")
async def admin_upload_clip(
    clip_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[AdminYouTubeUploadIn] = None,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Unggah klip (milik siapa pun) ke channel YouTube yang terhubung ke admin."""
    options = payload or AdminYouTubeUploadIn()

    try:
        cid = UUID(clip_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid clip id.")

    clip = (await db.execute(select(Clip).where(Clip.id == cid))).scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")
    if clip.youtube_uploaded and clip.youtube_video_id and not options.force:
        return {
            "success": True,
            "already_uploaded": True,
            "youtube_video_id": clip.youtube_video_id,
            "youtube_video_url": f"https://youtu.be/{clip.youtube_video_id}",
        }
    if not clip.download_url:
        raise HTTPException(status_code=400, detail="This clip has no video file to upload.")

    credential = (
        await db.execute(
            select(YouTubeCredential).where(YouTubeCredential.user_id == current_admin.id)
        )
    ).scalar_one_or_none()
    if credential is None:
        raise HTTPException(
            status_code=400,
            detail="Your admin account has no connected YouTube channel. Connect it from /profile first.",
        )

    access_token = decrypt_field(credential.access_token_encrypted)
    expiry = credential.token_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if not access_token or (expiry is not None and expiry <= datetime.now(timezone.utc) + timedelta(seconds=60)):
        refresh = (
            decrypt_field(credential.refresh_token_encrypted)
            if credential.refresh_token_encrypted
            else ""
        )
        tokens = await youtube_service.refresh_access_token(refresh)
        access_token = tokens["access_token"]
        credential.access_token_encrypted = encrypt_field(access_token)
        credential.token_expires_at = youtube_service.token_expiry(tokens.get("expires_in"))
        if tokens.get("refresh_token"):
            credential.refresh_token_encrypted = encrypt_field(tokens["refresh_token"])
        await db.commit()

    title = clip.ai_suggested_title or clip.title or "Shorts"
    description = clip.ai_suggested_description or ""
    tags = list(clip.ai_suggested_tags or [])
    if not clip.ai_suggested_title and isinstance(clip.viral_factors, dict):
        transcript = str(clip.viral_factors.get("transcript") or "").strip()
        if len(transcript.split()) >= 6:
            try:
                generated = await MetadataGenerator().generate(
                    transcript=transcript,
                    source_title=clip.title or "",
                    duration=float(clip.duration or 0),
                    start_time=clip.start_time or "",
                    end_time=clip.end_time or "",
                )
                title = generated["title"]
                description = generated["description"]
                tags = list(generated["tags"])
                clip.ai_suggested_title = title[:500]
                clip.ai_suggested_description = description
                clip.ai_suggested_tags = tags
                await db.commit()
            except MetadataGenerationError:
                pass

    _check_video_source(clip.download_url)

    job = YOUTUBE_UPLOAD_JOBS.setdefault(str(clip.id), {})
    job.update({"status": "uploading", "error": None, "video_id": None})
    background_tasks.add_task(
        _run_youtube_upload,
        clip.id,
        access_token,
        clip.download_url,
        title,
        description,
        list(tags),
        options.privacy_status,
        options.category_id,
        False,
    )
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="admin_youtube_upload_started",
            resource_type="clip",
            resource_id=str(clip.id),
            old_values=None,
            new_values={"privacy": options.privacy_status, "category": options.category_id},
        )
    )
    await db.commit()

    return JSONResponse(
        status_code=202,
        content={
            "accepted": True,
            "status": "uploading",
            "clip_id": str(clip.id),
            "message": "Upload started. Poll /api/admin/youtube/status/{clip_id}.",
        },
    )


@router.get("/status/{clip_id}")
async def admin_upload_status(
    clip_id: str,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Status unggahan klip untuk admin (setelah POST menerima 202)."""
    try:
        cid = UUID(clip_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid clip id.")

    clip = (await db.execute(select(Clip).where(Clip.id == cid))).scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    job = YOUTUBE_UPLOAD_JOBS.get(str(clip.id)) or {}
    video_id = clip.youtube_video_id or job.get("video_id")
    return {
        "clip_id": str(clip.id),
        "status": job.get("status") or ("done" if video_id else "idle"),
        "error": job.get("error"),
        "youtube_video_id": video_id,
        "youtube_video_url": f"https://youtu.be/{video_id}" if video_id else None,
    }
