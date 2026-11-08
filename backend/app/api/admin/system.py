"""
Admin system health endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session

router = APIRouter()


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db_session)):
    return {
        "status": "healthy",
        "database": "connected",
        "version": "1.0.0",
    }


@router.get("/stats")
async def system_stats(db: AsyncSession = Depends(get_db_session)):
    return {
        "total_users": 0,
        "total_tasks": 0,
        "total_clips": 0,
        "total_revenue": 0,
    }