"""Queue unggah YouTube: bulk sekarang atau terjadwal (Batch E10)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.db.session import AsyncSessionLocal
from app.models.clip import Clip
from app.models.scheduled_publish import ScheduledPublish
from app.models.task import Task
from app.models.youtube_credential import YouTubeCredential
from app.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)
youtube_service = YouTubeService()


async def _access_token(db: AsyncSession, user_id: UUID) -> str:
    result = await db.execute(
        select(YouTubeCredential).where(YouTubeCredential.user_id == user_id)
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        raise RuntimeError("YouTube is not connected for this account.")
    token = decrypt_field(credential.access_token_encrypted)
    expiry = credential.token_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if token and (expiry is None or expiry > datetime.now(timezone.utc) + timedelta(seconds=60)):
        return token
    refresh = (
        decrypt_field(credential.refresh_token_encrypted)
        if credential.refresh_token_encrypted
        else ""
    )
    tokens = await youtube_service.refresh_access_token(refresh)
    credential.access_token_encrypted = encrypt_field(tokens["access_token"])
    credential.token_expires_at = youtube_service.token_expiry(tokens.get("expires_in"))
    if tokens.get("refresh_token"):
        credential.refresh_token_encrypted = encrypt_field(tokens["refresh_token"])
    await db.commit()
    return str(tokens["access_token"])


async def _upload_row(db: AsyncSession, row: ScheduledPublish) -> None:
    row.status = "uploading"
    row.error = None
    await db.commit()

    clip = await db.get(Clip, row.clip_id)
    if clip is None or not clip.download_url:
        raise RuntimeError("Clip or its video file is missing.")

    token = await _access_token(db, row.user_id)
    scheduled_at = row.scheduled_at
    if scheduled_at is not None and scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    publish_at = None
    if scheduled_at and scheduled_at > datetime.now(timezone.utc) + timedelta(seconds=60):
        publish_at = scheduled_at

    title = (clip.ai_suggested_title or clip.title or "Shorts")[:100]
    description = clip.ai_suggested_description or ""
    tags = list(clip.ai_suggested_tags or [])
    uploaded = await youtube_service.upload_video(
        access_token=token,
        source_url=clip.download_url,
        title=title,
        description=description,
        tags=tags,
        privacy_status=row.privacy_status or "unlisted",
        category_id="22",
        made_for_kids=False,
        publish_at=publish_at,
    )
    clip.youtube_uploaded = True
    clip.youtube_video_id = uploaded["video_id"]
    row.status = "done"
    row.video_id = uploaded["video_id"]
    row.video_url = uploaded.get("video_url")
    row.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def process_due_scheduled(limit: int = 5) -> int:
    """Proses baris pending yang sudah waktunya. Return jumlah yang diproses."""
    processed = 0
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ScheduledPublish)
            .where(
                ScheduledPublish.status == "pending",
                ScheduledPublish.scheduled_at <= now,
            )
            .order_by(ScheduledPublish.scheduled_at.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        for row in rows:
            try:
                await _upload_row(db, row)
            except Exception as exc:
                await db.rollback()
                row = await db.get(ScheduledPublish, row.id)
                if row is not None:
                    row.status = "error"
                    row.error = str(exc)[:500]
                    await db.commit()
                logger.warning(
                    "Scheduled publish %s gagal: %s",
                    row.id if row else "?",
                    str(exc)[:300],
                )
            processed += 1
    return processed


async def scheduled_publish_scheduler() -> None:
    """Loop background di API untuk menjalankan jadwal upload."""
    while True:
        try:
            await process_due_scheduled()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Scheduler publish error: %s", str(exc)[:300])
        await asyncio.sleep(30)


async def enqueue_clips(
    db: AsyncSession,
    user_id: UUID,
    clip_ids: list[str],
    privacy_status: str = "unlisted",
    publish_at: Optional[datetime] = None,
) -> list[ScheduledPublish]:
    """Validasi kepemilikan klip lalu buat baris antrean."""
    parsed = []
    for raw in clip_ids[:50]:
        try:
            parsed.append(UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    if not parsed:
        raise ValueError("No valid clip ids were provided.")
    result = await db.execute(
        select(Clip)
        .join(Task, Clip.task_id == Task.id)
        .where(Clip.id.in_(parsed), Task.user_id == user_id)
    )
    found = {str(clip.id): clip for clip in result.scalars().all()}
    rows: list[ScheduledPublish] = []
    for cid in parsed:
        clip = found.get(str(cid))
        if clip is None:
            continue
        row = ScheduledPublish(
            user_id=user_id,
            clip_id=clip.id,
            platform="youtube",
            scheduled_at=publish_at or datetime.now(timezone.utc),
            status="pending",
            privacy_status=privacy_status,
        )
        db.add(row)
        rows.append(row)
    if not rows:
        raise ValueError("None of the selected clips belong to this account.")
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows
