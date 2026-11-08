"""
YtdlpCookie - penyimpanan cookies YouTube untuk rotasi otomatis.

Cookies disimpan TERENKRIPSI (AES-256-GCM) di database, bukan di .env, supaya:
  - bisa diganti tanpa redeploy
  - bisa menampung banyak akun (pool) dan dirotasi otomatis
  - token jangka pendek yang di-refresh YouTube bisa ditulis balik oleh yt-dlp

Status:
  active   -> dipakai untuk download
  expired  -> gagal (butuh cookies baru dari akun tsb)
  disabled -> dinonaktifkan manual oleh admin
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

COOKIE_STATUS_ACTIVE = "active"
COOKIE_STATUS_EXPIRED = "expired"
COOKIE_STATUS_DISABLED = "disabled"


class YtdlpCookie(Base):
    __tablename__ = "ytdlp_cookies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    # Isi cookies.txt (format Netscape) yang sudah dienkripsi AES-256-GCM
    encrypted_cookies: Mapped[str] = mapped_column(Text)

    status: Mapped[str] = mapped_column(
        String(20), default=COOKIE_STATUS_ACTIVE, index=True
    )
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Penanda bahwa cookies ini pernah ditulis balik oleh yt-dlp (token dirotasi)
    refreshed_by_ytdlp: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
