"""
ClipPerformance model - Social media performance analytics
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClipPerformance(Base):
    __tablename__ = "clip_performance"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id: Mapped[UUID] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(50))
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    watch_time_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    retention_rate: Mapped[float] = mapped_column(Float, default=0.0)
    revenue_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)