"""
Scheduled publish schemas
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ScheduledPublishCreate(BaseModel):
    clip_id: str
    platform: str  # youtube, tiktok, instagram, facebook
    scheduled_at: datetime


class ScheduledPublishResponse(BaseModel):
    id: str
    clip_id: str
    platform: str
    scheduled_at: datetime
    status: str
    external_post_id: Optional[str]
    external_post_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True