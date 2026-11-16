"""
Log worker GPU yang disimpan permanen untuk audit.

Instance Vast yang gagal boot tidak bisa dibaca lagi setelah dihapus, jadi
supervisor menyalin potongan log terakhir ke tabel ini (`worker_logs`) agar
admin masih bisa memeriksa penyebabnya kapan pun.

Tabel dibuat otomatis oleh `create_all()` — tanpa migrasi.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkerLog(Base):
    __tablename__ = "worker_logs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Baris worker boleh hilang bila task dihapus; log tetap disimpan (SET NULL).
    worker_instance_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("worker_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    instance_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # failed | cancelled | success
    outcome: Mapped[str] = mapped_column(String(16), default="failed", index=True)
    state: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gpu_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    log_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
