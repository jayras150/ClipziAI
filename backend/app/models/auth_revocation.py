"""
AuthRevocation - pencabutan sesi (logout, logout-all, paksa logout user).

JWT bersifat stateless: sekali diterbitkan, token berlaku sampai `exp`. Supaya
admin bisa mengeluarkan sesi lebih cepat (mis. akun dicurigai, user minta
logout semua perangkat), setiap user punya SATU baris di tabel ini berisi
`revoked_before`. Token dengan `iat` lebih lama dari nilai tersebut ditolak.

Tabel dibuat otomatis oleh `Base.metadata.create_all()` saat startup, jadi
tidak perlu migrasi manual untuk kolom baru pada tabel lama.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuthRevocation(Base):
    __tablename__ = "auth_revocations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    # Semua token yang diterbitkan sebelum waktu ini dianggap tidak berlaku.
    revoked_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
