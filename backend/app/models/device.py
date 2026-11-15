"""Device identity, account association, free-claim, and abuse events."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEVICE_STATUS_NEW = "NEW"
DEVICE_STATUS_TRUSTED = "TRUSTED"
DEVICE_STATUS_LOW = "LOW_RISK"
DEVICE_STATUS_SUSPICIOUS = "SUSPICIOUS"
DEVICE_STATUS_HIGH = "HIGH_RISK"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    reputation_score: Mapped[int] = mapped_column(Integer, default=0)
    reputation_status: Mapped[str] = mapped_column(String(24), default=DEVICE_STATUS_NEW, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class DeviceAccount(Base):
    __tablename__ = "device_accounts"
    __table_args__ = (UniqueConstraint("device_id", "user_id", name="uq_device_account"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DeviceFreeClaim(Base):
    __tablename__ = "device_free_claims"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), unique=True, index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="claimed")
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class DeviceEvent(Base):
    __tablename__ = "device_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


__all__ = [
    "DEVICE_STATUS_HIGH",
    "DEVICE_STATUS_LOW",
    "DEVICE_STATUS_NEW",
    "DEVICE_STATUS_SUSPICIOUS",
    "DEVICE_STATUS_TRUSTED",
    "Device",
    "DeviceAccount",
    "DeviceEvent",
    "DeviceFreeClaim",
]
