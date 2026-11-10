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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.api.youtube import _check_video_source
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

    uploaded = await youtube_service.upload_video(
        access_token=access_token,
        source_url=clip.download_url,
        title=title,
        description=description,
        tags=tags,
        privacy_status=options.privacy_status,
        category_id=options.category_id,
    )

    clip.youtube_uploaded = True
    clip.youtube_video_id = uploaded["video_id"]
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="admin_youtube_upload",
            resource_type="clip",
            resource_id=str(clip.id),
            old_values=None,
            new_values={"video_id": uploaded["video_id"], "privacy": options.privacy_status},
        )
    )
    await db.commit()

    return {
        "success": True,
        "youtube_video_id": uploaded["video_id"],
        "youtube_video_url": uploaded["video_url"],
        "title": title,
        "privacy_status": uploaded.get("privacy_status"),
    }
