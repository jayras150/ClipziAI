"""
BestTimeToPost model - Optimal posting time analytics
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BestTimeToPost(Base):
    __tablename__ = "best_time_to_post"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(50))
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0-6
    hour: Mapped[int] = mapped_column(Integer)  # 0-23
    avg_engagement: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)