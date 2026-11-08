"""
Plan Service - Feature gating and plan limit checks
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_profile import UserProfile, PlanType
from app.core.feature_gate import FeatureGate

class PlanService:
    """Check plan features and limits."""
    
    @staticmethod
    async def get_user_plan(db: AsyncSession, user_id: str) -> Optional[str]:
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        return profile.plan_type.value if profile else None
    
    @staticmethod
    async def is_feature_available(
        db: AsyncSession,
        user_id: str,
        feature_key: str,
    ) -> bool:
        plan_type = await PlanService.get_user_plan(db, user_id)
        if not plan_type:
            return False
        return FeatureGate.is_feature_available(plan_type, feature_key)
    
    @staticmethod
    async def get_locked_features(
        db: AsyncSession,
        user_id: str,
        requested_features: list,
    ) -> list:
        plan_type = await PlanService.get_user_plan(db, user_id)
        if not plan_type:
            return requested_features
        return FeatureGate.get_locked_features(plan_type, requested_features)
    
    @staticmethod
    async def get_plan_limits(db: AsyncSession, user_id: str) -> dict:
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        
        if not profile:
            return {
                "max_video_duration_minutes": 5,
                "max_concurrent_tasks": 1,
                "watermark": True,
                "priority_queue": False,
                "youtube_upload": False,
                "all_editing_features": False,
            }
        
        limits = {
            "free": {
                "max_video_duration_minutes": 5,
                "max_concurrent_tasks": 1,
                "watermark": True,
                "priority_queue": False,
                "youtube_upload": False,
                "all_editing_features": False,
            },
            "standar": {
                "max_video_duration_minutes": 30,
                "max_concurrent_tasks": 2,
                "watermark": False,
                "priority_queue": False,
                "youtube_upload": True,
                "all_editing_features": False,
            },
            "pro": {
                "max_video_duration_minutes": 60,
                "max_concurrent_tasks": 5,
                "watermark": False,
                "priority_queue": True,
                "youtube_upload": True,
                "all_editing_features": True,
            },
            "team": {
                "max_video_duration_minutes": 120,
                "max_concurrent_tasks": 10,
                "watermark": False,
                "priority_queue": True,
                "youtube_upload": True,
                "all_editing_features": True,
            },
        }
        return limits.get(profile.plan_type.value, limits["free"])