"""
Clip template schemas
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class ClipTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    editing_options: dict


class ClipTemplateResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    editing_options: dict
    is_public: bool
    usage_count: int
    created_at: datetime

    class Config:
        from_attributes = True