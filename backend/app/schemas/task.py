"""
Task schemas - Task CRUD
"""
from typing import Optional, List, Any
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class TaskCreate(BaseModel):
    source_url: HttpUrl
    source_type: str = "youtube"
    target_duration_min: Optional[int] = None
    target_duration_max: Optional[int] = None
    whisper_model: str = "small"
    output_format: str = "mp4"
    output_resolution: str = "1080x1920"
    fps: int = 30
    editing_options: Optional[dict] = None
    auto_upload_youtube: bool = False


class TaskResponse(BaseModel):
    id: str
    user_id: str
    source_url: str
    source_type: str
    status: str
    progress: int
    total_clips: Optional[int]
    error_message: Optional[str]
    auto_upload_youtube: bool
    youtube_upload_status: Optional[str]
    youtube_video_id: Optional[str]
    youtube_video_url: Optional[str]
    credits_spent: int
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int