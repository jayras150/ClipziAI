"""
YouTubeCredential model - OAuth2 tokens for YouTube upload
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class YouTubeCredential(Base):
    __tablename__ = "youtube_credentials"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    channel_id: Mapped[str] = mapped_column(String(100))
    channel_name: Mapped[str] = mapped_column(String(255))
    access_token_encrypted: Mapped[str] = mapped_column(String(2000))  # AES-256-GCM encrypted
    refresh_token_encrypted: Mapped[str] = mapped_column(String(2000))
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[str] = mapped_column(String(500), default="https://www.googleapis.com/auth/youtube.upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)