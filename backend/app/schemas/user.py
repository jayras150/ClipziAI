"""
User schemas - Profile, credits, plan
"""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class UserProfileResponse(BaseModel):
    id: str
    email: Optional[str]
    name: str
    avatar_url: Optional[str]
    plan_type: str
    credits_balance: int
    credits_total_earned: int
    credits_total_spent: int
    language: str
    timezone: str
    is_active: bool
    email_verified: bool
    two_factor_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None


class CreditBalanceResponse(BaseModel):
    credits_balance: int
    credits_total_earned: int
    credits_total_spent: int
    plan_type: str