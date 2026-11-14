"""
Runner downloader eksternal (GitHub Actions) — fallback saat Vast gagal.

Token/credential disimpan terenkripsi (AES-GCM via `encrypt_field`) dan tidak
pernah dikembalikan ke frontend maupun ditulis ke log.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DownloadRunner(Base):
    __tablename__ = "download_runners"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    runner_type: Mapped[str] = mapped_column(String(20), default="github")
    owner: Mapped[str] = mapped_column(String(120))
    repo: Mapped[str] = mapped_column(String(120))
    workflow_file: Mapped[str] = mapped_column(String(160), default="downloader_video.yml")
    git_ref: Mapped[str] = mapped_column(String(80), default="main")
    auth_mode: Mapped[str] = mapped_column(String(10), default="pat")
    token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    app_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    installation_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    private_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    weight: Mapped[int] = mapped_column(Integer, default=100)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_execution_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rate_limit_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_limit_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class RunnerJob(Base):
    __tablename__ = "runner_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    runner_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("download_runners.id", ondelete="SET NULL"), nullable=True
    )
    dispatch_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="dispatched", index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True
    )
