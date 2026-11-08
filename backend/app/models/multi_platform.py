"""
Multi-platform repurpose models
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlatformType(str, enum.Enum):
    YOUTUBE_SHORTS = "youtube_shorts"
    TIKTOK = "tiktok"
    INSTAGRAM_REELS = "instagram_reels"
    FACEBOOK_STORIES = "facebook_stories"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class OutputStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    ERROR = "error"


class MultiPlatformJob(Base):
    __tablename__ = "multi_platform_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.QUEUED)
    platforms: Mapped[List[str]] = mapped_column(JSONB)  # list of platform names
    total_outputs: Mapped[int] = mapped_column(Integer, default=0)
    completed_outputs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    outputs: Mapped[list["PlatformOutput"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class PlatformOutput(Base):
    __tablename__ = "platform_outputs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("multi_platform_jobs.id", ondelete="CASCADE"), index=True)
    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType))
    aspect_ratio: Mapped[str] = mapped_column(String(20), default="9:16")
    max_duration: Mapped[int] = mapped_column(Integer, default=60)
    resolution: Mapped[str] = mapped_column(String(20), default="1080x1920")
    clip_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("clips.id", ondelete="SET NULL"), nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[OutputStatus] = mapped_column(Enum(OutputStatus), default=OutputStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["MultiPlatformJob"] = relationship(back_populates="outputs")


class PlatformPreset(Base):
    __tablename__ = "platform_presets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    platform: Mapped[PlatformType] = mapped_column(Enum(PlatformType), unique=True)
    default_aspect_ratio: Mapped[str] = mapped_column(String(20), default="9:16")
    default_max_duration: Mapped[int] = mapped_column(Integer, default=60)
    default_resolution: Mapped[str] = mapped_column(String(20), default="1080x1920")
    recommended_settings: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.multi_platform import MultiPlatformJob
    from app.models.multi_platform import PlatformOutput
