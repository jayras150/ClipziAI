"""Scheduled YouTube publish queue (Batch E10)."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScheduledPublish(Base):
    """Satu klip yang menunggu diunggah/dijadwalkan ke platform.

    Tabel dibuat otomatis oleh ``init_db()`` (create_all), tanpa migrasi.
    Status: pending | uploading | done | error | cancelled.
    """

    __tablename__ = "scheduled_publishes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    clip_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(30), default="youtube")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    privacy_status: Mapped[str] = mapped_column(String(20), default="unlisted")
    payload: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    video_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
