"""
Admin task monitoring: daftar (filter + pagination), detail, cancel, retry.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.clip import Clip
from app.models.download_log import DownloadAttempt, TaskLog
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.services.download_errors import user_message_for
from app.services.vast_worker import dispatch_mode, submit_task

router = APIRouter(dependencies=[Depends(get_current_admin)])


async def _audit(db, request, admin, action, task_id: str, meta=None) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="task",
            resource_id=task_id,
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


def _serialize(task: Task, user_email: Optional[str]) -> dict:
    return {
        "id": str(task.id),
        "user_id": str(task.user_id),
        "user_email": user_email,
        "source_url": task.source_url,
        "source_type": task.source_type,
        "status": getattr(task.status, "value", str(task.status)),
        "download_status": task.download_status,
        "error_category": task.error_category,
        "user_message": task.user_message,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "next_retry_at": task.next_retry_at.isoformat() if task.next_retry_at else None,
        "progress": task.progress,
        "total_clips": task.total_clips,
        "credits_spent": task.credits_spent,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/")
async def list_all_tasks(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, description="Cari URL task / email user"),
    user_id: Optional[UUID] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Task, User.email).join(User, Task.user_id == User.id, isouter=True)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if user_id:
        query = query.where(Task.user_id == user_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Task.source_url.ilike(like), User.email.ilike(like)))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    rows = (
        await db.execute(
            query.order_by(Task.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return {
        "items": [_serialize(task, email) for task, email in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/{task_id}")
async def get_task_detail(task_id: UUID, db: AsyncSession = Depends(get_db_session)):
    row = (
        await db.execute(
            select(Task, User.email)
            .join(User, Task.user_id == User.id, isouter=True)
            .where(Task.id == task_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    task, email = row

    clips = (
        await db.execute(select(Clip).where(Clip.task_id == task_id).order_by(Clip.clip_index))
    ).scalars().all()

    return {
        **_serialize(task, email),
        "original_duration": task.original_duration,
        "target_duration_min": task.target_duration_min,
        "target_duration_max": task.target_duration_max,
        "plan_at_time": task.plan_at_time,
        "editing_options": task.editing_options,
        "youtube_upload_status": task.youtube_upload_status,
        "youtube_video_url": task.youtube_video_url,
        "clips": [
            {
                "id": str(c.id),
                "clip_index": c.clip_index,
                "title": c.title,
                "duration": c.duration,
                "download_url": getattr(c, "download_url", None),
                "thumbnail_url": getattr(c, "thumbnail_url", None),
            }
            for c in clips
        ],
    }


@router.get("/{task_id}/attempts")
async def list_download_attempts(
    task_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Semua percobaan download (full error, tanpa pemotongan) untuk viewer admin."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    rows = (
        await db.execute(
            select(DownloadAttempt)
            .where(DownloadAttempt.task_id == task_id)
            .order_by(DownloadAttempt.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "attempt_no": row.attempt_no,
            "runner_type": row.runner_type,
            "runner_id": row.runner_id,
            "yt_dlp_version": row.yt_dlp_version,
            "extractor_client": row.extractor_client,
            "format_selector": row.format_selector,
            "cookie_id": row.cookie_id,
            "cookie_status": row.cookie_status,
            "http_status": row.http_status,
            "error_category": row.error_category,
            "error_message": row.error_message,
            "stack_trace": row.stack_trace,
            "duration_ms": row.duration_ms,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/{task_id}/task-logs")
async def list_task_logs(
    task_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    rows = (
        await db.execute(
            select(TaskLog).where(TaskLog.task_id == task_id).order_by(TaskLog.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "level": row.level,
            "message": row.message,
            "meta": row.meta,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/{task_id}/download-log", response_class=PlainTextResponse)
async def download_log_text(
    task_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Unduh log download lengkap sebagai teks (tanpa ellipsis/pemotongan)."""
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    attempts = (
        await db.execute(
            select(DownloadAttempt)
            .where(DownloadAttempt.task_id == task_id)
            .order_by(DownloadAttempt.created_at)
        )
    ).scalars().all()

    lines = [
        f"Task ID        : {task.id}",
        f"User ID        : {task.user_id}",
        f"Video URL      : {task.source_url}",
        f"Status         : {getattr(task.status, 'value', str(task.status))}",
        f"Download status: {task.download_status}",
        f"Error category : {task.error_category}",
        f"Retry          : {task.retry_count}/{task.max_retries}",
        f"Created        : {task.created_at.isoformat() if task.created_at else '-'}",
        "",
        f"=== DOWNLOAD ATTEMPTS ({len(attempts)}) ===",
    ]
    for row in attempts:
        lines.extend(
            [
                "",
                f"--- attempt #{row.attempt_no} @ {row.created_at} ---",
                f"runner={row.runner_type} ({row.runner_id}) yt-dlp={row.yt_dlp_version}",
                f"client={row.extractor_client} format={row.format_selector}",
                f"cookie_id={row.cookie_id} cookie_status={row.cookie_status}",
                f"http_status={row.http_status} category={row.error_category}",
                "error:",
                row.error_message or "-",
                "stack:",
                row.stack_trace or "-",
            ]
        )
    return "\n".join(lines)


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.ERROR, TaskStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail="Task sudah selesai/gagal; tidak bisa dibatalkan."
        )

    before = getattr(task.status, "value", str(task.status))
    task.status = TaskStatus.CANCELLED
    await db.commit()
    await _audit(db, request, current_admin, "task_cancelled", str(task_id), {"from": before})
    return {"message": f"Task {task_id} dibatalkan", "status": "cancelled"}


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Kembalikan task gagal ke antrean (`queued`) supaya diproses ulang.
    Klip lama tidak dihapus agar hasil lama masih bisa dibandingkan.
    """
    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan")
    if task.status not in (TaskStatus.ERROR, TaskStatus.CANCELLED):
        raise HTTPException(
            status_code=400, detail="Hanya task error/cancelled yang bisa diulang."
        )

    before = getattr(task.status, "value", str(task.status))
    task.status = TaskStatus.QUEUED
    task.progress = 0
    task.error_message = None
    task.user_message = None
    task.error_category = None
    task.download_status = "queued"
    task.next_retry_at = None
    task.completed_at = None
    task.source_asset_url = None
    await db.commit()

    # Kirim ulang ke worker. Tanpa langkah ini task hanya berubah status jadi
    # `queued` dan TIDAK PERNAH diproses (tidak ada scheduler yang menarik
    # antrean), sehingga tombol Retry terlihat berhasil tapi task menggantung.
    dispatch = await submit_task(task.id)
    if not dispatch.get("queued"):
        task.status = TaskStatus.ERROR
        task.download_status = "failed"
        task.error_message = (
            f"Gagal mengirim ulang task ke worker (mode {dispatch_mode()}): "
            f"{dispatch.get('error') or 'tanpa keterangan'}"
        )
        task.user_message = user_message_for(None)
        await db.commit()

    await _audit(
        db,
        request,
        current_admin,
        "task_retried",
        str(task_id),
        {"from": before, "dispatch_mode": dispatch_mode(), "queued": bool(dispatch.get("queued"))},
    )
    if dispatch.get("queued"):
        return {
            "message": f"Task {task_id} dimasukkan kembali ke antrean",
            "status": "queued",
            "dispatch_mode": dispatch_mode(),
        }
    return {
        "message": f"Task {task_id} gagal dikirim ke worker: {task.error_message}",
        "status": "error",
        "dispatch_mode": dispatch_mode(),
    }
