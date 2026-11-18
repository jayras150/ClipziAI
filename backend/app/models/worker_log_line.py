"""Baris log mentah dari dalam instance worker (streaming)."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerLogLine(Base):
    __tablename__ = "worker_log_lines"
    __table_args__ = (UniqueConstraint("task_id", "seq", name="uq_worker_log_line_seq"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    instance_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    stage: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
