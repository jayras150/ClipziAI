"""
Multi-platform schemas
"""
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class PlatformPresetResponse(BaseModel):
    platform: str
    default_aspect_ratio: str
    default_max_duration: int
    default_resolution: str
    recommended_settings: Optional[dict]


class MultiPlatformJobCreate(BaseModel):
    source_task_id: str
    platforms: List[str]


class MultiPlatformJobResponse(BaseModel):
    id: str
    user_id: str
    source_task_id: str
    status: str
    platforms: List[str]
    total_outputs: int
    completed_outputs: int
    created_at: datetime

    class Config:
        from_attributes = True


class PlatformOutputResponse(BaseModel):
    id: str
    job_id: str
    platform: str
    aspect_ratio: str
    max_duration: int
    resolution: str
    download_url: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True