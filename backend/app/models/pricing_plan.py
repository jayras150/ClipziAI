"""
PricingPlan model - Subscription plans
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, Integer, Text, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PricingPlan(Base):
    __tablename__ = "pricing_plans"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Enum("free", "standar", "pro", "team", name="plan_names"), unique=True, index=True)
    display_name: Mapped[dict] = mapped_column(JSONB)  # localized per language
    description: Mapped[dict] = mapped_column(JSONB)  # localized per language
    price_monthly: Mapped[int] = mapped_column(Integer)  # IDR
    price_yearly: Mapped[int] = mapped_column(Integer)  # IDR
    credits_monthly: Mapped[int] = mapped_column(Integer)
    max_video_duration_minutes: Mapped[int] = mapped_column(Integer)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer)
    watermark: Mapped[bool] = mapped_column(Boolean, default=True)
    priority_queue: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_upload: Mapped[bool] = mapped_column(Boolean, default=False)
    all_editing_features: Mapped[bool] = mapped_column(Boolean, default=False)
    team_seats: Mapped[int] = mapped_column(Integer, default=1)
    features_list: Mapped[List[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    subscriptions: Mapped[list["UserSubscription"]] = relationship(back_populates="plan")


if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.user_subscription import UserSubscription