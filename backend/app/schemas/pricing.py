"""
Pricing schemas - Plans, subscriptions
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class PricingPlanResponse(BaseModel):
    id: str
    name: str
    display_name: dict
    description: dict
    price_monthly: int
    price_yearly: int
    credits_monthly: int
    max_video_duration_minutes: int
    max_concurrent_tasks: int
    watermark: bool
    priority_queue: bool
    youtube_upload: bool
    all_editing_features: bool
    team_seats: int
    features_list: List[str]
    is_active: bool

    class Config:
        from_attributes = True


class SubscribeRequest(BaseModel):
    plan_id: str
    payment_method: Optional[str] = None


class SubscriptionResponse(BaseModel):
    id: str
    plan_id: str
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True