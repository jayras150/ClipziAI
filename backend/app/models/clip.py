"""
Clip model - Individual short video clips
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, Float, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    clip_index: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(20))  # HH:MM:SS
    end_time: Mapped[str] = mapped_column(String(20))  # HH:MM:SS
    duration: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(255))
    download_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subtitle_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    viral_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    viral_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_suggested_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_suggested_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_suggested_tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    youtube_uploaded: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    editing_applied: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    task: Mapped["Task"] = relationship(back_populates="clips")


if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.task import Task