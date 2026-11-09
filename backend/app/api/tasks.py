"""
Task endpoints - Create, get, list, delete tasks
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from uuid import UUID

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.clip import Clip
from app.models.user_profile import UserProfile
from app.schemas.task import TaskCreate, TaskResponse, TaskListResponse
from app.schemas.clip import ClipResponse
from app.schemas.common import MessageResponse
from app.services.vast_worker import dispatch_mode, submit_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # Get user profile for plan limits
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    
    if not profile:
        raise HTTPException(status_code=404, detail="User profile not found")
    
    # Check concurrent task limit
    result = await db.execute(
        select(func.count(Task.id)).where(
            Task.user_id == current_user.id,
            Task.status.in_(["queued", "processing"])
        )
    )
    active_count = result.scalar() or 0
    
    if active_count >= profile.max_concurrent_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {profile.max_concurrent_tasks} concurrent tasks allowed for your plan",
        )
    
    # Check credits
    if profile.credits_balance < 1:
        raise HTTPException(
            status_code=400,
            detail="Insufficient credits. Please upgrade your plan or purchase more credits.",
        )
    
    # Kumpulkan opsi editing ke JSONB (tidak perlu migrasi DB)
    editing_options = dict(task_data.editing_options or {})
    if task_data.start_time is not None:
        editing_options["start_time"] = task_data.start_time
    if task_data.end_time is not None:
        editing_options["end_time"] = task_data.end_time
    if task_data.aspect_ratio:
        editing_options["aspect_ratio"] = task_data.aspect_ratio
    if task_data.caption_text:
        editing_options["caption_text"] = task_data.caption_text
    if task_data.speed != 1.0:
        editing_options["speed"] = task_data.speed

    # ---------- Fase 2: gaya & polish ----------
    if task_data.filter_preset:
        editing_options["filter_preset"] = task_data.filter_preset
    if task_data.blur_fill:
        editing_options["blur_fill"] = True
    if task_data.remove_silence:
        editing_options["remove_silence"] = True
    if task_data.enhance_audio:
        editing_options["enhance_audio"] = True
    if task_data.watermark_url:
        editing_options["watermark_url"] = task_data.watermark_url
        editing_options["watermark_position"] = task_data.watermark_position
        editing_options["watermark_opacity"] = task_data.watermark_opacity
        editing_options["watermark_scale"] = task_data.watermark_scale
    if task_data.intro_url:
        editing_options["intro_url"] = task_data.intro_url
    if task_data.outro_url:
        editing_options["outro_url"] = task_data.outro_url

    # ---------- Auto zoom follow-speaker ----------
    if task_data.auto_zoom:
        editing_options["auto_zoom"] = task_data.auto_zoom
        if task_data.zoom_level and task_data.zoom_level != 1.0:
            editing_options["zoom_level"] = task_data.zoom_level

    # Create task
    task = Task(
        user_id=current_user.id,
        source_url=str(task_data.source_url),
        source_type=task_data.source_type,
        status=TaskStatus.QUEUED,
        target_duration_min=task_data.target_duration_min,
        target_duration_max=task_data.target_duration_max,
        whisper_model=task_data.whisper_model,
        output_format=task_data.output_format,
        output_resolution=task_data.output_resolution,
        fps=task_data.fps,
        editing_options=editing_options,
        auto_upload_youtube=task_data.auto_upload_youtube,
        plan_at_time=profile.plan_type.value,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Kirim job ke worker GPU (Vast.ai serverless) — tidak memblokir respons.
    # Task sudah tersimpan lebih dulu, jadi user tetap bisa melihatnya walaupun
    # dispatch gagal.
    dispatch = await submit_task(task.id)
    if not dispatch.get("queued"):
        # Job tidak pernah sampai ke worker. Tandai error supaya frontend tidak
        # menampilkan "queued" selamanya (tidak ada scheduler yang me-retry
        # otomatis), dan pesan penyebabnya tersimpan untuk ditampilkan.
        task.status = TaskStatus.ERROR
        task.error_message = (
            f"Gagal mengirim task ke worker (mode {dispatch_mode()}): "
            f"{dispatch.get('error') or 'tanpa keterangan'}"
        )
        await db.commit()
        await db.refresh(task)
        logger.error("Task %s gagal didispatch: %s", task.id, task.error_message)

    logger.info(
        "Task %s dibuat (mode dispatch=%s, queued=%s)",
        task.id,
        dispatch_mode(),
        dispatch.get("queued"),
    )

    return task


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == current_user.id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task


@router.get("/{task_id}/clips", response_model=List[ClipResponse])
async def list_task_clips(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Klip hasil pemrosesan sebuah task — dipakai dashboard untuk menampilkan hasil."""
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == current_user.id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    clips_result = await db.execute(select(Clip).where(Clip.task_id == task.id).order_by(Clip.clip_index))
    clips = clips_result.scalars().all()

    return [
        ClipResponse(
            id=str(clip.id),
            task_id=str(clip.task_id),
            clip_index=clip.clip_index,
            start_time=clip.start_time,
            end_time=clip.end_time,
            duration=clip.duration,
            title=clip.title,
            download_url=clip.download_url,
            subtitle_url=clip.subtitle_url,
            thumbnail_url=clip.thumbnail_url,
            file_size=clip.file_size,
            viral_score=clip.viral_score,
            viral_factors=clip.viral_factors,
            ai_suggested_title=clip.ai_suggested_title,
            ai_suggested_description=clip.ai_suggested_description,
            ai_suggested_tags=clip.ai_suggested_tags,
            youtube_uploaded=clip.youtube_uploaded,
            youtube_video_id=clip.youtube_video_id,
            editing_applied=clip.editing_applied,
            created_at=clip.created_at,
        )
        for clip in clips
    ]


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    offset = (page - 1) * page_size
    
    result = await db.execute(
        select(Task).where(Task.user_id == current_user.id)
        .order_by(Task.created_at.desc())
        .offset(offset).limit(page_size)
    )
    tasks = result.scalars().all()
    
    count_result = await db.execute(
        select(func.count(Task.id)).where(Task.user_id == current_user.id)
    )
    total = count_result.scalar() or 0
    
    return TaskListResponse(
        tasks=[TaskResponse.model_validate(task) for task in tasks],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == current_user.id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await db.delete(task)
    await db.commit()
    
    return MessageResponse(message="Task deleted successfully")