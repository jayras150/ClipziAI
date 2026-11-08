"""
Multi-platform repurpose endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.multi_platform import (
    MultiPlatformJobCreate, MultiPlatformJobResponse, PlatformOutputResponse, PlatformPresetResponse
)

router = APIRouter()


@router.post("/job", response_model=MultiPlatformJobResponse)
async def create_multi_platform_job(
    job_data: MultiPlatformJobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Implement multi-platform job creation
    return MultiPlatformJobResponse(
        id="placeholder",
        user_id=str(current_user.id),
        source_task_id=job_data.source_task_id,
        status="queued",
        platforms=job_data.platforms,
        total_outputs=len(job_data.platforms),
        completed_outputs=0,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/job/{job_id}", response_model=MultiPlatformJobResponse)
async def get_multi_platform_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Fetch from DB
    return MultiPlatformJobResponse(
        id=job_id,
        user_id=str(current_user.id),
        source_task_id="",
        status="processing",
        platforms=["youtube_shorts", "tiktok"],
        total_outputs=2,
        completed_outputs=0,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/presets", response_model=List[PlatformPresetResponse])
async def get_platform_presets():
    return [
        PlatformPresetResponse(
            platform="youtube_shorts",
            default_aspect_ratio="9:16",
            default_max_duration=60,
            default_resolution="1080x1920",
            recommended_settings={},
        ),
        PlatformPresetResponse(
            platform="tiktok",
            default_aspect_ratio="9:16",
            default_max_duration=60,
            default_resolution="1080x1920",
            recommended_settings={},
        ),
        PlatformPresetResponse(
            platform="instagram_reels",
            default_aspect_ratio="9:16",
            default_max_duration=90,
            default_resolution="1080x1920",
            recommended_settings={},
        ),
        PlatformPresetResponse(
            platform="facebook_stories",
            default_aspect_ratio="9:16",
            default_max_duration=120,
            default_resolution="1080x1920",
            recommended_settings={},
        ),
    ]