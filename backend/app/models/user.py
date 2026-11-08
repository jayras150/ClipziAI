"""
User model - Authentication & profile
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AuthProvider(str, enum.Enum):
    EMAIL = "email"
    GOOGLE = "google"
    X = "x"
    FACEBOOK = "facebook"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider), default=AuthProvider.EMAIL)
    provider_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    lock_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    subscriptions: Mapped[list["UserSubscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    credit_transactions: Mapped[list["CreditTransaction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["UserAPIKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    webhook_subscriptions: Mapped[list["WebhookSubscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    gdpr_requests: Mapped[list["GDPRRequest"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="user", cascade="all, delete-orphan")