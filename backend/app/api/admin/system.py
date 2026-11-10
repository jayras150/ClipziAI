"""
Admin system health + statistik nyata (bukan stub 0).

Dipakai dashboard admin (Batch D) untuk kartu statistik & grafik "task per hari".
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.clip import Clip
from app.models.task import Task, TaskStatus
from app.models.user import User

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db_session)):
    return {"status": "healthy", "database": "connected", "version": "1.0.0"}


@router.get("/stats")
async def system_stats(db: AsyncSession = Depends(get_db_session)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    banned_users = (
        await db.execute(select(func.count(User.id)).where(User.is_banned.is_(True)))
    ).scalar() or 0
    total_tasks = (await db.execute(select(func.count(Task.id)))).scalar() or 0
    total_clips = (await db.execute(select(func.count(Clip.id)))).scalar() or 0
    credits_spent = (
        await db.execute(select(func.coalesce(func.sum(Task.credits_spent), 0)))
    ).scalar() or 0

    status_rows = (
        await db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status))
    ).all()
    by_status = {getattr(s, "value", str(s)): int(c) for s, c in status_rows}

    since = datetime.now(timezone.utc) - timedelta(days=14)
    day_rows = (
        await db.execute(
            select(func.date_trunc("day", Task.created_at).label("day"), func.count(Task.id))
            .where(Task.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    tasks_per_day = [
        {"date": day.date().isoformat() if day else None, "count": int(count)}
        for day, count in day_rows
    ]

    recent_rows = (
        await db.execute(
            select(Task, User.email)
            .join(User, Task.user_id == User.id, isouter=True)
            .order_by(Task.created_at.desc())
            .limit(5)
        )
    ).all()
    recent_tasks = [
        {
            "id": str(task.id),
            "source_type": task.source_type,
            "status": getattr(task.status, "value", str(task.status)),
            "progress": task.progress,
            "total_clips": task.total_clips,
            "user_email": email,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        for task, email in recent_rows
    ]

    return {
        "total_users": int(total_users),
        "banned_users": int(banned_users),
        "total_tasks": int(total_tasks),
        "total_clips": int(total_clips),
        "credits_spent": float(credits_spent),
        "tasks_by_status": by_status,
        "tasks_per_day": tasks_per_day,
        "recent_tasks": recent_tasks,
        "completed_tasks": int(by_status.get(TaskStatus.COMPLETED.value, 0)),
    }
