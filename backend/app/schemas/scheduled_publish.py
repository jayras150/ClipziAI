"""
Scheduled publish schemas
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ScheduledPublishCreate(BaseModel):
    clip_id: str
    platform: str = "youtube"  # youtube only (Batch E10)
    scheduled_at: datetime
    privacy_status: str = "unlisted"


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