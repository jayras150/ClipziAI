"""
Bulk job schemas
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class BulkJobCreate(BaseModel):
    source_url: str
    total_clips_target: int


class BulkJobResponse(BaseModel):
    id: str
    user_id: str
    source_url: str
    total_clips_target: int
    status: str
    completed_clips: int
    created_at: datetime

    class Config:
        from_attributes = True