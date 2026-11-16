"""Registry model Whisper (CT2) yang tersimpan di Google Drive.

Satu baris = satu folder model di Drive. Folder aktif menentukan sumber
`cloud_copy` Vast saat instance worker dibuat, sehingga admin bisa mengganti
model tanpa membangun ulang image.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WhisperModel(Base):
    __tablename__ = "whisper_models"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    provider: Mapped[str] = mapped_column(String(24), default="gdrive", index=True)
    drive_folder_id: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    drive_path: Mapped[str] = mapped_column(String(400))
    model_type: Mapped[str] = mapped_column(String(20), default="ct2")
    status: Mapped[str] = mapped_column(String(24), default="available", index=True)
    validation_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    files: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - bantu debugging
        return f"<WhisperModel {self.slug} ({self.status})>"

    # Nama generik agar kode multi-provider tidak perlu tahu istilah "drive".
    @property
    def remote_id(self) -> str:
        return str(self.drive_folder_id or "")

    @property
    def remote_path(self) -> str:
        return str(self.drive_path or "")

    @property
    def source(self) -> str:
        return str(self.provider or "gdrive")


__all__ = ["WhisperModel"]
