"""
GDPRRequest model - Data export/deletion requests
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GDPRRequestType(str, enum.Enum):
    DATA_EXPORT = "data_export"
    DATA_DELETION = "data_deletion"
    ACCOUNT_DELETION = "account_deletion"


class GDPRRequestStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"


class GDPRRequest(Base):
    __tablename__ = "gdpr_requests"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    request_type: Mapped[GDPRRequestType] = mapped_column(Enum(GDPRRequestType))
    status: Mapped[GDPRRequestStatus] = mapped_column(Enum(GDPRRequestStatus), default=GDPRRequestStatus.PENDING)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.user import User
    user: Mapped["User"] = relationship(back_populates="gdpr_requests")