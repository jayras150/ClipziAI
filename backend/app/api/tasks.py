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
from app.models.user_profile import UserProfile
from app.schemas.task import TaskCreate, TaskResponse, TaskListResponse
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
        editing_options=task_data.editing_options,
        auto_upload_youtube=task_data.auto_upload_youtube,
        plan_at_time=profile.plan_type.value,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Kirim job ke worker GPU (Vast.ai serverless) — tidak memblokir respons.
    # Bila dispatch gagal, task tetap tersimpan (status queued) dan error hanya
    # dicatat di log agar bisa di-retry manual.
    dispatch = await submit_task(task.id)
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