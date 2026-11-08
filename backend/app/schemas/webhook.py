"""
Webhook schemas
"""
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class WebhookSubscriptionCreate(BaseModel):
    url: str
    events: List[str]


class WebhookSubscriptionResponse(BaseModel):
    id: str
    user_id: str
    url: str
    events: List[str]
    is_active: bool
    last_triggered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True