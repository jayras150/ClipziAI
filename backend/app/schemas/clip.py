"""
Clip schemas - Clip details
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class ClipResponse(BaseModel):
    id: str
    task_id: str
    clip_index: int
    start_time: str
    end_time: str
    duration: float
    title: str
    download_url: Optional[str]
    subtitle_url: Optional[str]
    thumbnail_url: Optional[str]
    file_size: Optional[int]
    viral_score: Optional[float]
    viral_factors: Optional[dict]
    ai_suggested_title: Optional[str]
    ai_suggested_description: Optional[str]
    ai_suggested_tags: Optional[List[str]]
    youtube_uploaded: bool
    youtube_video_id: Optional[str]
    editing_applied: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True