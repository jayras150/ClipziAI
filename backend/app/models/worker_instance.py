"""
Riwayat instance GPU Vast.ai per task.

Dipakai supervisor untuk audit & diagnosa: mesin mana yang gagal boot, berapa
percobaan, harga yang dibayar, dan potongan log terakhir saat gagal. Tabel baru
otomatis dibuat `create_all()` — tanpa migrasi.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerInstance(Base):
    __tablename__ = "worker_instances"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    instance_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    offer_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    machine_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gpu_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    price_per_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(24), default="creating")
    status_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    log_tail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    destroy_reason: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ready_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    destroyed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
