"""
CreditTransaction model - Credit ledger
"""
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CreditTransactionType(str, enum.Enum):
    SIGNUP_BONUS = "signup_bonus"
    SUBSCRIPTION = "subscription"
    PURCHASE = "purchase"
    TASK_SPENT = "task_spent"
    REFUND = "refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)  # positive = earned, negative = spent
    type: Mapped[CreditTransactionType] = mapped_column(Enum(CreditTransactionType))
    description: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # localized
    task_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    admin_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)  # admin who adjusted
    balance_after: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


if TYPE_CHECKING:  # hanya untuk type checker (hindari circular import)
    from app.models.user import User
    user: Mapped["User"] = relationship(back_populates="credit_transactions")