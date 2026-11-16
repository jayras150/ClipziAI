"""Admin API - notifikasi nyata (task gagal, worker error, runner, Vast)."""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.services import notifications

router = APIRouter(dependencies=[Depends(get_current_admin)])


class ReadNotificationsIn(BaseModel):
    keys: List[str] = []


@router.get("")
async def read_notifications(db: AsyncSession = Depends(get_db_session)):
    return await notifications.build_notifications(db)


@router.post("/read")
async def mark_notifications_read(
    payload: ReadNotificationsIn,
    db: AsyncSession = Depends(get_db_session),
):
    return await notifications.mark_read(db, payload.keys)


@router.post("/read-all")
async def mark_all_notifications_read(db: AsyncSession = Depends(get_db_session)):
    return await notifications.mark_all_read(db)
