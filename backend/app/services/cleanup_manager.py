"""
Cleanup cloud storage yang aman & idempotent.

Aturan:
  - Hanya `task_assets` kind source/audio/temp yang boleh dihapus.
  - Klip hasil, thumbnail, dan aset berstatus protected TIDAK pernah dihapus.
  - File sumber dipertahankan bila clipping gagal (menunggu retry/TTL).
  - Scheduler menghapus sisa file yatim lebih tua dari TEMP_TTL_HOURS.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.task import Task
from app.models.task_asset import TaskAsset
from app.services.storage_registry import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()

_TEMP_KINDS = ("source", "audio", "temp")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def register_asset(
    db: AsyncSession,
    task_id: UUID,
    storage_key: str,
    kind: str = "temp",
    size_bytes: Optional[int] = None,
) -> TaskAsset:
    asset = TaskAsset(
        task_id=task_id,
        storage_key=storage_key,
        kind=kind,
        size_bytes=size_bytes,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def cleanup_task_temp(db: AsyncSession, task_id: UUID) -> dict:
    """Hapus source/audio/temp setelah SEMUA klip berhasil dibuat."""
    rows = (
        await db.execute(
            select(TaskAsset).where(
                TaskAsset.task_id == task_id,
                TaskAsset.deleted_at.is_(None),
                TaskAsset.protected.is_(False),
                TaskAsset.kind.in_(_TEMP_KINDS),
            )
        )
    ).scalars().all()

    deleted = 0
    failed = 0
    storage = get_storage()
    for asset in rows:
        if settings.CLEANUP_DRY_RUN:
            logger.info("[cleanup dry-run] akan hapus %s (%s)", asset.storage_key, asset.kind)
            continue
        try:
            ok = storage.delete_file(asset.storage_key)
        except Exception as exc:  # storage error tidak boleh menggagalkan pipeline
            logger.warning("Cleanup gagal untuk %s: %s", asset.storage_key, exc)
            ok = False
        if ok:
            asset.deleted_at = _now()
            deleted += 1
        else:
            failed += 1
    if not settings.CLEANUP_DRY_RUN:
        await db.commit()
    return {"deleted": deleted, "failed": failed, "candidates": len(rows)}


async def sweep_orphans() -> dict:
    """Hapus aset yatim (task selesai/gagal atau lebih tua dari TTL)."""
    from app.db.session import AsyncSessionLocal

    cutoff = _now() - timedelta(hours=max(1, settings.TEMP_TTL_HOURS))
    deleted = 0
    failed = 0
    checked = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(TaskAsset, Task)
                .join(Task, Task.id == TaskAsset.task_id)
                .where(
                    TaskAsset.deleted_at.is_(None),
                    TaskAsset.protected.is_(False),
                    TaskAsset.kind.in_(_TEMP_KINDS),
                )
            )
        ).all()
        storage = get_storage()
        for asset, task in rows:
            checked += 1
            status = getattr(task.status, "value", str(task.status))
            task_finished = status in ("completed", "error", "cancelled")
            too_old = asset.created_at and asset.created_at < cutoff
            if not (task_finished or too_old):
                # Task masih berjalan: file mungkin masih dibutuhkan.
                continue
            if settings.CLEANUP_DRY_RUN:
                logger.info("[cleanup dry-run] orphan %s", asset.storage_key)
                continue
            try:
                ok = storage.delete_file(asset.storage_key)
            except Exception as exc:
                logger.warning("Cleanup orphan gagal %s: %s", asset.storage_key, exc)
                ok = False
            if ok:
                asset.deleted_at = _now()
                deleted += 1
            else:
                failed += 1
        if not settings.CLEANUP_DRY_RUN:
            await db.commit()
    return {"checked": checked, "deleted": deleted, "failed": failed}


async def cleanup_scheduler() -> None:
    """Loop background di API; interval dari CLEANUP_INTERVAL_MINUTES."""
    interval = max(5, settings.CLEANUP_INTERVAL_MINUTES) * 60
    while True:
        try:
            result = await sweep_orphans()
            if result.get("deleted") or result.get("failed"):
                logger.info("Cleanup storage: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - loop harus tetap hidup
            logger.warning("Cleanup scheduler error: %s", exc)
        await asyncio.sleep(interval)
