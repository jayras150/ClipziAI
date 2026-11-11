"""
Jejak pemakaian tombol "Regenerate with AI" pada metadata klip.

Kenapa tabel terpisah (bukan kolom di clips): `viral_factors` bisa ditimpa saat
skor dihitung ulang, sedangkan kuota regenerate harus tetap utuh dan bisa
diaudit. Tabel baru otomatis dibuat oleh `create_all()` — tanpa migrasi.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiRegenerateLog(Base):
    __tablename__ = "ai_regenerate_log"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    clip_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clips.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
