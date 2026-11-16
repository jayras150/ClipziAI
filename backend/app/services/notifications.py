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
                "detail": str(row.detail or row.category or "")[:4000],
                "href": f"/dashboard/tasks?task={row.id}",
                "created_at": _iso(row.happened_at),
                "kind": "task",
                "log_ref": {"type": "task", "id": str(row.id)},
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
                "detail": message[:4000],
                "href": "/dashboard/workers",
                "created_at": _iso(row.created_at),
                "kind": "worker",
                "log_ref": {"type": "worker", "id": str(row.id)},
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
            "detail": str(row.last_error)[:4000],
            "href": "/dashboard/settings/runners",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": "runner",
            "log_ref": {"type": "runner", "id": str(row.id)},
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
                "detail": "Env template worker Vast belum lengkap: "
                + ", ".join(str(name) for name in missing),
                "href": "/dashboard/settings/vast",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "kind": "vast",
            }
        )
    return items


async def _worker_log_items(db: AsyncSession) -> List[Dict[str, Any]]:
    """Log worker yang sudah disimpan (audit) — muncul juga di lonceng."""
    try:
        rows = (
            await db.execute(
                text(
                    """
                    select id::text as id, instance_id, coalesce(reason, '') as reason,
                           coalesce(gpu_name, '') as gpu_name, created_at
                    from worker_logs
                    where outcome in ('failed', 'cancelled')
                      and created_at >= now() - interval '24 hours'
                    order by created_at desc
                    limit 5
                    """
                )
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifikasi worker_logs dilewati: %s", exc)
        return []
    items: List[Dict[str, Any]] = []
    for row in rows:
        reason = str(row.reason or "").strip() or "Worker gagal tanpa pesan."
        items.append(
            {
                "key": f"worker_log:{row.id}",
                "severity": "error",
                "title": f"Worker gagal: instance {row.instance_id or '-'}"
                + (f" ({row.gpu_name})" if row.gpu_name else ""),
                "body": reason[:300],
                "detail": reason[:4000],
                "href": "/dashboard/workers",
                "created_at": _iso(row.created_at),
                "kind": "worker_log",
                "log_ref": {"type": "worker_log", "id": str(row.id)},
            }
        )
    return items


async def _security_items(db: AsyncSession) -> List[Dict[str, Any]]:
    try:
        rows = (
            await db.execute(
                text(
                    """
                    select id::text as id, event_type::text as event_type,
                           risk_level::text as risk_level, ip_address, created_at,
                           coalesce(details::text, '') as details
                    from security_events
                    where is_resolved = false
                      and created_at >= now() - interval '24 hours'
                    order by created_at desc
                    limit 5
                    """
                )
            )
        ).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifikasi security dilewati: %s", exc)
        return []
    items: List[Dict[str, Any]] = []
    for row in rows:
        severity = "error" if str(row.risk_level or "").upper() in {"HIGH", "CRITICAL"} else "warning"
        items.append(
            {
                "key": f"security:{row.id}",
                "severity": severity,
                "title": f"Security: {row.event_type} ({row.risk_level})",
                "body": f"IP {row.ip_address or '-'}: {str(row.details or '')[:200]}",
                "detail": str(row.details or "")[:4000],
                "href": "/dashboard/notifications",
                "created_at": _iso(row.created_at),
                "kind": "security",
                "log_ref": {"type": "security", "id": str(row.id)},
            }
        )
    return items


async def log_for(db: AsyncSession, key: str) -> Dict[str, Any]:
    """Detail + log lengkap untuk satu notifikasi (tombol "Cek Log")."""
    kind, _, ident = str(key or "").partition(":")
    payload: Dict[str, Any] = {
        "key": key,
        "kind": kind,
        "title": "",
        "severity": "info",
        "created_at": "",
        "detail": "",
        "log_text": "",
        "related": {},
    }

    if kind == "task" and ident:
        row = (
            await db.execute(
                text(
                    """
                    select id::text as id, status::text as status, source_url,
                           coalesce(error_message, '') as error_message,
                           coalesce(user_message, '') as user_message,
                           coalesce(error_category, '') as error_category,
                           coalesce(retry_count, 0) as retry_count,
                           coalesce(updated_at, created_at) as happened_at
                    from tasks where id = cast(:ident as uuid)
                    """
                ),
                {"ident": ident},
            )
        ).first()
        if row is None:
            return {**payload, "detail": "Task tidak ditemukan (mungkin sudah dihapus)."}
        lines = [
            f"Task: {row.id}",
            f"Status: {row.status}",
            f"Sumber: {row.source_url or '-'}",
            f"Kategori: {row.error_category or '-'}",
            f"Retry: {row.retry_count}",
            "",
            "Pesan untuk user:",
            str(row.user_message or "-"),
            "",
            "Error internal:",
            str(row.error_message or "-"),
        ]
        return {
            **payload,
            "title": f"Task {row.status}",
            "severity": "error" if row.status == "FAILED" else "warning",
            "created_at": _iso(row.happened_at),
            "detail": str(row.error_message or row.user_message or ""),
            "log_text": "\n".join(lines),
            "related": {"task_id": row.id, "href": f"/dashboard/tasks?task={row.id}"},
        }

    if kind == "worker_log" and ident:
        from uuid import UUID as _UUID

        from app.models.worker_log import WorkerLog
        from app.services import worker_logs as wl

        try:
            row = await db.get(WorkerLog, _UUID(ident))
        except (ValueError, AttributeError, TypeError):
            row = None
        if row is None:
            return {**payload, "detail": "Log worker tidak ditemukan (mungkin sudah dihapus)."}
        data = wl.serialize(row, with_log=True)
        return {
            **payload,
            "title": f"Worker {data['outcome']} — instance {data['instance_id'] or '-'}",
            "severity": "error" if data["outcome"] == "failed" else "warning",
            "created_at": data["created_at"] or "",
            "detail": str(data.get("reason") or ""),
            "log_text": str(data.get("log_text") or ""),
            "related": {"instance_id": data["instance_id"], "href": "/dashboard/workers"},
        }

    if kind == "worker" and ident:
        row = (
            await db.execute(
                text(
                    """
                    select instance_id, state::text as state, coalesce(status_msg, '') as status_msg,
                           coalesce(log_tail, '') as log_tail, created_at
                    from worker_instances where instance_id::text = :ident
                    order by created_at desc limit 1
                    """
                ),
                {"ident": ident},
            )
        ).first()
        if row is None:
            return {**payload, "detail": "Instance tidak ditemukan."}
        return {
            **payload,
            "title": f"Worker {row.state} — instance {row.instance_id}",
            "severity": "error",
            "created_at": _iso(row.created_at),
            "detail": str(row.status_msg or ""),
            "log_text": str(row.log_tail or ""),
            "related": {"instance_id": row.instance_id, "href": "/dashboard/workers"},
        }

    if kind == "runner" and ident:
        row = (
            await db.execute(
                text(
                    """
                    select id::text as id, name, coalesce(last_error, '') as last_error,
                           base_url
                    from download_runners where id::text = :ident
                    """
                ),
                {"ident": ident},
            )
        ).first()
        if row is None:
            return {**payload, "detail": "Runner tidak ditemukan."}
        return {
            **payload,
            "title": f"Runner: {row.name}",
            "severity": "warning",
            "detail": str(row.last_error or ""),
            "log_text": "\n".join(
                [
                    f"Runner: {row.name}",
                    f"URL: {row.base_url or '-'}",
                    "",
                    str(row.last_error or "-"),
                ]
            ),
            "related": {"href": "/dashboard/settings/runners"},
        }

    if kind == "security" and ident:
        row = (
            await db.execute(
                text(
                    """
                    select event_type::text as event_type, risk_level::text as risk_level,
                           ip_address, user_agent, coalesce(details::text, '') as details,
                           created_at
                    from security_events where id::text = :ident
                    """
                ),
                {"ident": ident},
            )
        ).first()
        if row is None:
            return {**payload, "detail": "Security event tidak ditemukan."}
        return {
            **payload,
            "title": f"Security: {row.event_type} ({row.risk_level})",
            "severity": "error" if str(row.risk_level).upper() in {"HIGH", "CRITICAL"} else "warning",
            "created_at": _iso(row.created_at),
            "detail": str(row.details or ""),
            "log_text": "\n".join(
                [
                    f"Event: {row.event_type}",
                    f"Risk: {row.risk_level}",
                    f"IP: {row.ip_address or '-'}",
                    f"UA: {row.user_agent or '-'}",
                    "",
                    str(row.details or "-"),
                ]
            ),
            "related": {"href": "/dashboard/notifications"},
        }

    return {**payload, "detail": "Tidak ada log tambahan untuk notifikasi ini."}


async def build_notifications(db: AsyncSession) -> Dict[str, Any]:
    """Daftar notifikasi nyata + jumlah yang belum dibaca."""
    items: List[Dict[str, Any]] = []
    for loader in (_task_items, _worker_items, _worker_log_items, _security_items, _runner_items):
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


__all__ = ["build_notifications", "log_for", "mark_all_read", "mark_read"]