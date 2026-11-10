"""
PlatformSetting — setelan platform yang bisa diubah admin (key/value JSONB).

Dipakai pertama untuk konfigurasi watermark plan free, tapi dibuat generik
supaya setelan lain (mis. batas kredit, mode maintenance) tinggal menambah key.
Tabel dibuat otomatis oleh `init_db()` (Base.metadata.create_all).
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - bantu debugging
        return f"<PlatformSetting {self.key}>"


__all__ = ["PlatformSetting"]
