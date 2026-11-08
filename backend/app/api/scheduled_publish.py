"""
Scheduled publish endpoints
"""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.scheduled_publish import ScheduledPublishCreate, ScheduledPublishResponse

router = APIRouter()


@router.post("/", response_model=ScheduledPublishResponse)
async def create_scheduled_publish(
    publish_data: ScheduledPublishCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Create scheduled publish job
    return ScheduledPublishResponse(
        id="placeholder",
        clip_id=publish_data.clip_id,
        platform=publish_data.platform,
        scheduled_at=publish_data.scheduled_at,
        status="pending",
        external_post_id=None,
        external_post_url=None,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/", response_model=List[ScheduledPublishResponse])
async def list_scheduled_publishes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return []