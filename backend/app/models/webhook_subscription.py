"""
WebhookSubscription model - User webhook subscriptions
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    events: Mapped[List[str]] = mapped_column(JSONB, default=list)  # ["task.completed", "task.failed", ...]
    secret: Mapped[str] = mapped_column(String(500))  # for signature verification
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="webhook_subscriptions")