"""
Supported formats endpoint
"""
from fastapi import APIRouter
from app.schemas.common import FormatsResponse
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/formats", response_model=FormatsResponse)
async def get_formats():
    return FormatsResponse(
        supported_formats=["mp4"],
        supported_resolutions=["1080x1920", "1080x1080", "1080x1350"],
        max_duration_minutes=settings.MAX_VIDEO_DURATION_MINUTES,
        max_file_size_mb=settings.MAX_FILE_SIZE_MB,
    )