"""Notifikasi admin dari data nyata (bukan template).

Sumber:
- task gagal/cancelled 24 jam terakhir,
- instance worker Vast yang error,
- runner download yang punya `last_error`,
- env wajib template worker belum lengkap.

Status "sudah dibaca" disimpan di `platform_settings` (key
`admin_notifications_read`) sehingga tidak perlu tabel baru.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import platform_settings as ps

logger = logging.getLogger(__name__)

READ_KEY = "admin_notifications_read"
MAX_ITEMS = 20
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


async def _read_keys(db: AsyncSession) -> Dict[str, str]:
    raw = await ps.get_setting(db, READ_KEY, {})
    keys = raw.get("keys") if isinstance(raw, dict) else {}
    return keys if isinstance(keys, dict) else {}


async def _task_items(db: AsyncSession) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            text(
                """
                select id::text as id, source_url,
                       coalesce(nullif(user_message, ''), nullif(error_message, ''), '') as detail,
                       coalesce(error_category, '') as category, status::text as status,
                       coalesce(updated_at, created_at) as happened_at
                from tasks
                where status::text in ('FAILED', 'CANCELLED')
                  and coalesce(updated_at, created_at) >= now() - interval '24 hours'
                order by coalesce(updated_at, created_at) desc
                limit 8
                """
            )
        )
    ).all()
    items: List[Dict[str, Any]] = []
    for row in rows:
        source = str(row.source_url or "")
        short = source.split("?")[0][-60:] or "tanpa URL"
        label = "Task gagal" if row.status == "FAILED" else "Task dibatalkan"
        items.append(
            {
                "key": f"task:{row.id}",
                "severity": "error" if row.status == "FAILED" else "warning",
                "title": f"{label}: {short}",
                "body": str(row.detail or row.category or "Lihat detail task.")[:300],
                "href": f"/dashboard/tasks?task={row.id}",
                "created_at": _iso(row.happened_at),
                "kind": "task",
            }
        )
    return items


async def _worker_items(db: AsyncSession) -> List[Dict[str, Any]]:
    try:
        rows = (
            await db.execute(
                text(
                    """
                    select instance_id::text as id, state::text as state,
                           coalesce(status_msg, '') as message, created_at
                    from worker_instances
                    where lower(state::text) in ('error', 'failed', 'timeout', 'exited')
                      and created_at >= now() - interval '24 hours'
                    order by created_at desc
                    limit 5
                    """
                )
            )
        ).all()
    except Exception as exc:  # noqa: BLE001 - jangan gagalkan panel notifikasi
        logger.warning("notifikasi worker dilewati: %s", exc)
        return []
    items: List[Dict[str, Any]] = []
    for row in rows:
        message = str(row.message or "").strip()
        if not message:
            continue
        items.append(
            {
                "key": f"worker:{row.id}",
                "severity": "error",
                "title": f"Worker Vast {row.state}: instance {row.id}",
                "body": message[:300],
                "href": "/dashboard/settings/vast",
                "created_at": _iso(row.created_at),
                "kind": "worker",
            }
        )
    return items


async def _runner_items(db: AsyncSession) -> List[Dict[str, Any]]:
    try:
        rows = (
            await db.execute(
                text(
                    """
                    select id::text as id, name, coalesce(last_error, '') as last_error
                    from download_runners
                    where coalesce(last_error, '') <> ''
                    order by coalesce(updated_at, created_at) desc
                    limit 3
                    """
                )
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifikasi runner dilewati: %s", exc)
        return []
    return [
        {
            "key": f"runner:{row.id}",
            "severity": "warning",
            "title": f"Runner download bermasalah: {row.name}",
            "body": str(row.last_error)[:300],
            "href": "/dashboard/settings/runners",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": "runner",
        }
        for row in rows
    ]


def _vast_items() -> List[Dict[str, Any]]:
    try:
        from app.services import vast_admin

        spec = vast_admin.worker_template_spec()
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifikasi Vast dilewati: %s", exc)
        return []
    items: List[Dict[str, Any]] = []
    missing = spec.get("missing_required") or []
    if missing:
        items.append(
            {
                "key": "vast:env",
                "severity": "warning",
                "title": "Env worker Vast belum lengkap",
                "body": "Wajib diisi: " + ", ".join(str(name) for name in missing[:8]),
                "href": "/dashboard/settings/vast",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "kind": "vast",
            }
        )
    return items


async def build_notifications(db: AsyncSession) -> Dict[str, Any]:
    """Daftar notifikasi nyata + jumlah yang belum dibaca."""
    items: List[Dict[str, Any]] = []
    for loader in (_task_items, _worker_items, _runner_items):
        try:
            items.extend(await loader(db))
        except Exception as exc:  # noqa: BLE001 - satu sumber gagal ≠ panel kosong
            logger.warning("notifikasi %s gagal: %s", loader.__name__, exc)
    items.extend(_vast_items())

    read = await _read_keys(db)
    for item in items:
        item["read"] = item["key"] in read
    items.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 3),
            "1" if item.get("read") else "0",
            item.get("created_at") or "",
        )
    )
    items = items[:MAX_ITEMS]
    return {
        "items": items,
        "unread_count": sum(1 for item in items if not item.get("read")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def mark_read(db: AsyncSession, keys: List[str]) -> Dict[str, Any]:
    stored = await ps.get_setting(db, READ_KEY, {})
    existing = stored.get("keys") if isinstance(stored, dict) else {}
    existing = existing if isinstance(existing, dict) else {}
    now = datetime.now(timezone.utc).isoformat()
    for key in keys or []:
        text_key = str(key or "").strip()
        if text_key:
            existing[text_key] = now
    await ps.set_setting(db, READ_KEY, {"keys": existing})
    await db.commit()
    return {"ok": True, "read": len(existing)}


async def mark_all_read(db: AsyncSession) -> Dict[str, Any]:
    data = await build_notifications(db)
    return await mark_read(db, [item["key"] for item in data["items"]])


__all__ = ["build_notifications", "mark_all_read", "mark_read"]