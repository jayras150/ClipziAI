"""
Model observability downloader:
  - DownloadAttempt : satu catatan per percobaan yt-dlp (full error, admin-only)
  - TaskLog         : log kronologis task (level, pesan, metadata)
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DownloadAttempt(Base):
    __tablename__ = "download_attempts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    runner_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    runner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    yt_dlp_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    extractor_client: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    format_selector: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    cookie_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cookie_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
