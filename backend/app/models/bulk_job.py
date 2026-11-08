"""
BulkJob model - Bulk video processing
"""
import enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BulkJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BulkJob(Base):
    __tablename__ = "bulk_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_url: Mapped[str] = mapped_column(String(500))
    total_clips_target: Mapped[int] = mapped_column(Integer)
    status: Mapped[BulkJobStatus] = mapped_column(Enum(BulkJobStatus), default=BulkJobStatus.QUEUED)
    completed_clips: Mapped[int] = mapped_column(Integer, default=0)
    clips: Mapped[Optional[List[UUID]]] = mapped_column(JSONB, nullable=True)  # list of clip IDs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)