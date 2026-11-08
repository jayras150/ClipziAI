"""
API key schemas
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class APIKeyCreate(BaseModel):
    key_name: str
    rate_limit_per_minute: Optional[int] = 60
    rate_limit_per_day: Optional[int] = 1000
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    id: str
    key_name: str
    key_prefix: str
    rate_limit_per_minute: int
    rate_limit_per_day: int
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyRawResponse(BaseModel):
    raw_key: str
    key_prefix: str