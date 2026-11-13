"""
Task endpoints - Create, get, list, delete tasks
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional
from uuid import UUID

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.clip import Clip
from app.models.user_profile import UserProfile
from app.schemas.task import (
    ComposeRequest,
    SplitRequest,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
)
from app.schemas.clip import ClipResponse
from app.schemas.common import MessageResponse
from app.services.vast_worker import dispatch_mode, submit_task
from app.services.viral import score_clip

logger = logging.getLogger(__name__)

router = APIRouter()

# Kunci `editing_options` yang benar-benar dipakai pipeline/worker. Key lain
# (typo dari klien) dibuang + dicatat, supaya tidak "hilang diam-diam".
ALLOWED_EDITING_OPTIONS = {
    "start_time", "end_time", "aspect_ratio", "caption_text", "caption_style",
    "caption_color", "caption_size", "caption_font", "speed",
    "filter_preset", "blur_fill", "remove_silence", "enhance_audio",
    "watermark_url", "watermark_position", "watermark_opacity", "watermark_scale",
    "intro_url", "outro_url", "auto_zoom", "zoom_level",
    "music_url", "music_volume", "music_ducking",
    "max_clips", "burn_subtitle", "segments",
    "target_duration_min", "target_duration_max",
}


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
    raw_options = dict(task_data.editing_options or {})
    unknown_keys = sorted(set(raw_options) - ALLOWED_EDITING_OPTIONS)
    if unknown_keys:
        logger.warning(
            "Task baru: opsi editing tidak dikenal diabaikan: %s", unknown_keys
        )
    editing_options = {
        key: value for key, value in raw_options.items() if key in ALLOWED_EDITING_OPTIONS
    }
    if task_data.start_time is not None:
        editing_options["start_time"] = task_data.start_time
    if task_data.end_time is not None:
        editing_options["end_time"] = task_data.end_time
    if task_data.aspect_ratio:
        editing_options["aspect_ratio"] = task_data.aspect_ratio
    if task_data.caption_text:
        editing_options["caption_text"] = task_data.caption_text
    # Gaya subtitle juga berguna tanpa caption manual karena ikut menata
    # subtitle SRT yang dibakar dari transkrip.
    if task_data.caption_style:
        editing_options["caption_style"] = task_data.caption_style
    if task_data.speed != 1.0:
        editing_options["speed"] = task_data.speed

    # Panjang klip = jendela target (soft). Hasil akhir mengikuti akhir kalimat,
    # jadi boleh 1:03 / 1:16 — minimal 60 detik supaya klip > 1 menit.
    if task_data.target_duration_min is not None:
        editing_options["target_duration_min"] = max(60, int(task_data.target_duration_min))
    if task_data.target_duration_max is not None:
        editing_options["target_duration_max"] = max(60, int(task_data.target_duration_max))

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

    # ---------- Musik latar ----------
    if task_data.music_url:
        editing_options["music_url"] = task_data.music_url
        editing_options["music_volume"] = task_data.music_volume
        editing_options["music_ducking"] = task_data.music_ducking

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

    # Klip lama (dibuat sebelum fitur skor viral ada) dihitung saat pertama kali
    # dibuka. Transkrip tidak disimpan di DB, jadi ini estimasi dari durasi +
    # subtitle + caption; klip baru memakai skor penuh dari transkrip.
    backfilled = False
    for clip in clips:
        if clip.viral_score is None:
            estimated = score_clip(
                transcript="",
                duration=float(clip.duration or 0),
                has_subtitle=bool(clip.subtitle_url),
                has_caption=bool(clip.editing_applied),
                estimated=True,
            )
            clip.viral_score = estimated["score"]
            clip.viral_factors = estimated["factors"]
            backfilled = True
    if backfilled:
        await db.commit()

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
            ai_hook=(clip.viral_factors or {}).get("ai_hook")
            or (clip.viral_factors or {}).get("llm_hook"),
            ai_viral_reason=(clip.viral_factors or {}).get("ai_viral_reason")
            or (clip.viral_factors or {}).get("llm_reason"),
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


# =============================================================================
# Editing lanjutan: compose (gabung klip) & split (potong klip)
#
# Keduanya membuat TASK BARU lalu mengirimkannya ke worker GPU Vast.ai — VPS
# tidak pernah merender apa pun. Progres dipantau lewat endpoint task biasa.
# =============================================================================


async def _ensure_user_credits(profile: Optional[UserProfile], needed: float) -> None:
    if profile is None:
        raise HTTPException(status_code=404, detail="User profile not found")
    if float(profile.credits_balance) < needed:
        raise HTTPException(
            status_code=400,
            detail="Insufficient credits. Please upgrade your plan or purchase more credits.",
        )


async def _new_editing_task(
    current_user: User,
    db: AsyncSession,
    source_task: Task,
    options: dict,
    title_hint: str,
) -> Task:
    """Buat task baru berisi editing_options untuk compose/split, lalu dispatch."""
    task = Task(
        user_id=current_user.id,
        source_url=source_task.source_url,
        source_type=source_task.source_type,
        status=TaskStatus.QUEUED,
        output_format=source_task.output_format,
        output_resolution=source_task.output_resolution,
        fps=source_task.fps,
        editing_options=options,
        auto_upload_youtube=False,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    dispatch = await submit_task(task.id)
    if not dispatch.get("queued"):
        task.status = TaskStatus.ERROR
        task.error_message = (
            f"Gagal mengirim {title_hint} ke worker (mode {dispatch_mode()}): "
            f"{dispatch.get('error') or 'tanpa keterangan'}"
        )
        await db.commit()
    return task


@router.post("/{task_id}/compose", response_model=TaskResponse)
async def compose_task_clips(
    task_id: UUID,
    payload: ComposeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Gabungkan klip-klip hasil satu task menjadi satu video (dengan transisi)."""
    source_task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if not source_task:
        raise HTTPException(status_code=404, detail="Task not found")

    clip_ids = [str(cid) for cid in payload.clip_ids]
    if len(clip_ids) < 2:
        raise HTTPException(status_code=400, detail="Minimal 2 klip untuk digabung")

    found = (
        await db.execute(
            select(Clip).where(Clip.id.in_([UUID(cid) for cid in clip_ids]), Clip.task_id == task_id)
        )
    ).scalars().all()
    if len({str(clip.id) for clip in found}) != len(clip_ids):
        raise HTTPException(status_code=400, detail="One or more clip IDs are not valid for this task")

    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    await _ensure_user_credits(profile, 1.0)

    options = {
        "mode": "compose",
        "clip_ids": clip_ids,
        "transition": payload.transition,
        "transition_duration": payload.transition_duration,
        "aspect_ratio": payload.aspect_ratio,
        "music_volume": payload.music_volume,
        "music_ducking": payload.music_ducking,
        "watermark_position": payload.watermark_position,
        "watermark_opacity": payload.watermark_opacity,
        "watermark_scale": payload.watermark_scale,
    }
    if payload.music_url:
        options["music_url"] = payload.music_url
    if payload.watermark_url:
        options["watermark_url"] = payload.watermark_url

    return await _new_editing_task(current_user, db, source_task, options, "compose")


@router.post("/{task_id}/split", response_model=TaskResponse)
async def split_task_clip(
    task_id: UUID,
    payload: SplitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Potong satu klip menjadi dua bagian di detik `at_time`."""
    source_task = (
        await db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == current_user.id)
        )
    ).scalar_one_or_none()
    if not source_task:
        raise HTTPException(status_code=404, detail="Task not found")

    clip = (
        await db.execute(
            select(Clip).where(Clip.id == payload.clip_id, Clip.task_id == task_id)
        )
    ).scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found in this task")

    if payload.at_time >= float(clip.duration or 0):
        raise HTTPException(
            status_code=400,
            detail=f"at_time harus lebih kecil dari durasi klip ({clip.duration:.2f}s)",
        )

    profile = (
        await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    ).scalar_one_or_none()
    await _ensure_user_credits(profile, 2.0)

    options = {
        "mode": "split",
        "clip_id": str(payload.clip_id),
        "at_time": payload.at_time,
    }
    return await _new_editing_task(current_user, db, source_task, options, "split")
