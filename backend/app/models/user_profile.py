"""
UserProfile model - Plan, credits, settings
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, Integer, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlanType(str, enum.Enum):
    FREE = "free"
    STANDAR = "standar"
    PRO = "pro"
    TEAM = "team"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    plan_type: Mapped[PlanType] = mapped_column(Enum(PlanType), default=PlanType.FREE)
    credits_balance: Mapped[int] = mapped_column(Integer, default=0)
    credits_total_earned: Mapped[int] = mapped_column(Integer, default=0)
    credits_total_spent: Mapped[int] = mapped_column(Integer, default=0)
    credits_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    credits_reset_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duitku_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=1)
    watermark_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(10), default="id")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Jakarta")
    plan_features_locked: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")