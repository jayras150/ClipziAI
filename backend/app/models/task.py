"""
Task model - Video processing tasks
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, Float, Boolean, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaskStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(50))  # youtube, tiktok, instagram, facebook, vimeo, file
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.QUEUED, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    target_duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_duration_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    whisper_model: Mapped[str] = mapped_column(String(20), default="small")
    output_format: Mapped[str] = mapped_column(String(10), default="mp4")
    output_resolution: Mapped[str] = mapped_column(String(20), default="1080x1920")
    fps: Mapped[int] = mapped_column(Integer, default=30)
    original_duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_clips: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # --- Download observability & retry (Batch X) ---------------------------
    # Status granular fase download (queued/downloading/download_failed/
    # downloaded/processing/completed/failed/cancelled) tanpa mengubah ENUM DB.
    download_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True, index=True)
    error_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    # Pesan aman untuk user (tanpa detail teknis). error_message tetap teknis.
    user_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # URL objek hasil download oleh runner eksternal (GitHub Actions).
    source_asset_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auto_upload_youtube: Mapped[bool] = mapped_column(Boolean, default=False)
    youtube_upload_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    youtube_video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    editing_options: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    plan_at_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="tasks")
    clips: Mapped[list["Clip"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    @property
    def can_retry(self) -> bool:
        """User boleh mencoba lagi selama belum melewati batas retry."""
        status = getattr(self.status, "value", str(self.status))
        return status in ("error", "cancelled") and (self.retry_count or 0) < (
            self.max_retries or 0
        )
if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.clip import Clip
    from app.models.user import User
