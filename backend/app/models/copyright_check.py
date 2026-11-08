"""
CopyrightCheck model - Copyright scanning results
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Float, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CopyrightStatus(str, enum.Enum):
    CLEAN = "clean"
    FLAGGED = "flagged"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class CopyrightAction(str, enum.Enum):
    NONE = "none"
    WARNING = "warning"
    BLOCKED = "blocked"
    REMOVED = "removed"


class CopyrightCheck(Base):
    __tablename__ = "copyright_checks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    content_type: Mapped[str] = mapped_column(String(20))  # audio, video, image
    status: Mapped[CopyrightStatus] = mapped_column(Enum(CopyrightStatus), default=CopyrightStatus.CLEAN)
    detected_source: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    action_taken: Mapped[CopyrightAction] = mapped_column(Enum(CopyrightAction), default=CopyrightAction.NONE)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)