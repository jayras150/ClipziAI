"""
AdminUser model - Admin RBAC
"""
import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Boolean, Integer, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MODERATOR = "moderator"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.MODERATOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    two_factor_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    can_adjust_credits: Mapped[bool] = mapped_column(Boolean, default=False)
    can_ban_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_plans: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_audit: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    lock_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)