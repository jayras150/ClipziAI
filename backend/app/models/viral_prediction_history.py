"""
ViralPredictionHistory model - Track AI viral score predictions vs actual
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ViralPredictionHistory(Base):
    __tablename__ = "viral_prediction_history"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id: Mapped[UUID] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), index=True)
    predicted_score: Mapped[float] = mapped_column(Float)
    actual_performance: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)