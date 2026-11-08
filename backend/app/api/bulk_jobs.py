"""
Bulk job endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.bulk_job import BulkJobCreate, BulkJobResponse

router = APIRouter()


@router.post("/", response_model=BulkJobResponse)
async def create_bulk_job(
    job_data: BulkJobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Create bulk job
    return BulkJobResponse(
        id="placeholder",
        user_id=str(current_user.id),
        source_url=job_data.source_url,
        total_clips_target=job_data.total_clips_target,
        status="queued",
        completed_clips=0,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/", response_model=List[BulkJobResponse])
async def list_bulk_jobs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return []