"""
AuditLog model - Complete audit trail for all user and admin actions
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActorType(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_type: Mapped[ActorType] = mapped_column(Enum(ActorType), index=True)
    actor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)  # video_upload, task_created, credit_deducted, etc.
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # task, clip, user, transaction
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    meta_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # editing_options, credits_spent, viral_score, etc.
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    geolocation: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    session_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)