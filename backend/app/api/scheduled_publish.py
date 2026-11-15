"""
Scheduled publish endpoints (Batch E10).

Baris disimpan di `scheduled_publishes`; scheduler di API memproses yang sudah
jatuh tempo. Saat ini platform yang didukung adalah YouTube.
"""
from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.clip import Clip
from app.models.scheduled_publish import ScheduledPublish
from app.models.task import Task
from app.models.user import User
from app.schemas.scheduled_publish import ScheduledPublishCreate, ScheduledPublishResponse

router = APIRouter()


def _serialize(row: ScheduledPublish) -> ScheduledPublishResponse:
    return ScheduledPublishResponse(
        id=str(row.id),
        clip_id=str(row.clip_id),
        platform=row.platform,
        scheduled_at=row.scheduled_at,
        status=row.status,
        external_post_id=row.video_id,
        external_post_url=row.video_url,
        created_at=row.created_at,
    )


@router.post("/", response_model=ScheduledPublishResponse)
async def create_scheduled_publish(
    publish_data: ScheduledPublishCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    if (publish_data.platform or "").lower() != "youtube":
        raise HTTPException(
            status_code=400,
            detail="Only YouTube scheduled publishing is available right now.",
        )
    try:
        clip_id = UUID(publish_data.clip_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid clip id.")
    clip = (
        await db.execute(
            select(Clip)
            .join(Task, Clip.task_id == Task.id)
            .where(Clip.id == clip_id, Task.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")
    if not clip.download_url:
        raise HTTPException(status_code=400, detail="This clip has no video file.")

    row = ScheduledPublish(
        user_id=current_user.id,
        clip_id=clip.id,
        platform="youtube",
        scheduled_at=publish_data.scheduled_at,
        status="pending",
        privacy_status=publish_data.privacy_status or "unlisted",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.get("/", response_model=List[ScheduledPublishResponse])
async def list_scheduled_publishes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(ScheduledPublish)
        .where(ScheduledPublish.user_id == current_user.id)
        .order_by(ScheduledPublish.scheduled_at.desc())
    )
    return [_serialize(row) for row in result.scalars().all()]


@router.delete("/{publish_id}", response_model=ScheduledPublishResponse)
async def cancel_scheduled_publish(
    publish_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        pid = UUID(publish_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid scheduled publish id.")
    row = (
        await db.execute(
            select(ScheduledPublish).where(
                ScheduledPublish.id == pid,
                ScheduledPublish.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Scheduled publish not found.")
    if row.status in {"done", "uploading"}:
        raise HTTPException(status_code=409, detail="This job can no longer be cancelled.")
    row.status = "cancelled"
    await db.commit()
    await db.refresh(row)
    return _serialize(row)
