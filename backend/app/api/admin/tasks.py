"""
Admin task monitoring endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_db_session
from app.models.task import Task, TaskStatus

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=List[dict])
async def list_all_tasks(
    db: AsyncSession = Depends(get_db_session),
    status_filter: Optional[str] = None,
):
    query = select(Task)
    if status_filter:
        query = query.where(Task.status == status_filter)
    
    result = await db.execute(query.order_by(Task.created_at.desc()).limit(100))
    tasks = result.scalars().all()
    
    return [
        {
            "id": str(t.id),
            "user_id": str(t.user_id),
            "source_url": t.source_url,
            "status": t.status.value,
            "progress": t.progress,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.status = TaskStatus.CANCELLED
    await db.commit()
    
    return {"message": f"Task {task_id} cancelled"}