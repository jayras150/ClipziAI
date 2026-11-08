"""
ContentModeration model - Content moderation results
"""
import enum
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModerationStatus(str, enum.Enum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    REJECTED = "rejected"
    UNDER_REVIEW = "under_review"


class ContentModeration(Base):
    __tablename__ = "content_moderation"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    moderation_type: Mapped[str] = mapped_column(String(20), default="automated")  # automated, manual
    status: Mapped[ModerationStatus] = mapped_column(Enum(ModerationStatus), default=ModerationStatus.UNDER_REVIEW)
    flags: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)  # ["adult", "violence", "spam"]
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)