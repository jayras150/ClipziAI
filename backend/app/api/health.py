"""
Health check endpoint
"""
from fastapi import APIRouter
from app.schemas.common import HealthResponse
from app.core.config import get_settings
from app.core.redis import ping_redis

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    redis_ok = await ping_redis()
    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        version=settings.APP_VERSION,
        redis="connected" if redis_ok else "unavailable",
        gpu_available=False,
    )