"""
Analytics schemas
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class ClipPerformanceResponse(BaseModel):
    id: str
    clip_id: str
    platform: str
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_minutes: float
    retention_rate: float
    revenue_estimate: float
    recorded_at: datetime

    class Config:
        from_attributes = True


class ViralPredictionResponse(BaseModel):
    clip_id: str
    predicted_score: float
    factors: Optional[dict]
    created_at: datetime

    class Config:
        from_attributes = True


class BestTimeToPostResponse(BaseModel):
    platform: str
    day_of_week: int
    hour: int
    avg_engagement: float
    sample_size: int