"""Operasional Vast.ai untuk admin: instance live, log, billing, env, test."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.services.vast_config import normalize_allowlist
from app.services.vast_worker import (
    WORKER_ENV_OPTIONAL,
    WORKER_ENV_REQUIRED,
    _get_vast_client,
    build_worker_env,
)

logger = logging.getLogger(__name__)

RESERVED_ENV = {"PORT", "HOST"}


def _client():
    key = (get_settings().VAST_API_KEY or "").strip()
    if not key:
        raise RuntimeError(
            "VAST_API_KEY belum diset. Isi lewat Settings › Vast.ai atau backend/.env."
        )
    return _get_vast_client()


async def list_connections() -> List[Dict[str, str]]:
    """Koneksi Cloud Sync milik akun Vast (hanya id + nama, tanpa token)."""
    client = _client()
    try:
        rows = await asyncio.to_thread(client.show_connections)
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil koneksi Vast: {exc}") from exc
    items: List[Dict[str, str]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        connection_id = str(row.get("id") or "").strip()
        if not connection_id:
            continue
        items.append(
            {
                "id": connection_id,
                "name": str(row.get("name") or connection_id).strip(),
            }
        )
    items.sort(key=lambda item: item["id"])
    return items


async def detect_connection() -> Dict[str, Any]:
    """Deteksi koneksi yang cocok dengan konfigurasi restore saat ini."""
    from app.services.vast_worker import pick_connection_id

    settings = get_settings()
    configured = (settings.VAST_RESTORE_CONNECTION or "").strip()
    connections = await list_connections()
    try:
        selected = pick_connection_id(connections, configured)
        error = None
    except RuntimeError as exc:
        selected = None
        error = str(exc)
    return {
        "connections": connections,
        "configured": configured,
        "valid": bool(configured) and any(item["id"] == configured for item in connections),
        "selected": selected,
        "error": error,
    }


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(value)
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


async def live_instances() -> List[Dict[str, Any]]:
    """Instance yang benar-benar ada di akun Vast (bukan hanya riwayat lokal)."""
    client = _client()
    try:
        rows = await asyncio.to_thread(client.show_instances)
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil instance Vast: {exc}") from exc
    items: List[Dict[str, Any]] = []
    for row in rows or []:
        items.append(
            {
                "instance_id": row.get("id"),
                "machine_id": row.get("machine_id"),
                "gpu_name": row.get("gpu_name"),
                "num_gpus": row.get("num_gpus"),
                "price_per_hour": _number(row.get("dph_total")),
                "disk_space": _number(row.get("disk_space")),
                "disk_util": _number(row.get("disk_util")),
                "gpu_util": _number(row.get("gpu_util")),
                "state": row.get("actual_status") or row.get("cur_state"),
                "status_msg": row.get("status_msg"),
                "label": row.get("label"),
                "start_date": _iso(row.get("start_date")),
                "uptime": _number(row.get("uptime")),
                "image": row.get("image_uuid"),
            }
        )
    items.sort(key=lambda item: item.get("instance_id") or 0, reverse=True)
    return items


async def instance_logs(instance_id: int, tail: int = 300, daemon: bool = False) -> str:
    """Log container instance; `daemon=True` menampilkan daemon/engine logs."""
    client = _client()
    size = max(50, min(2000, int(tail or 300)))
    try:
        text = await asyncio.to_thread(
            client.logs, int(instance_id), str(size), None, daemon
        )
    except TypeError:
        text = await asyncio.to_thread(
            client.logs, int(instance_id), tail=str(size), daemon_logs=daemon
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil log instance {instance_id}: {exc}") from exc
    return (text or "").strip()


async def test_connection() -> Dict[str, Any]:
    try:
        client = _client()
        user = await asyncio.to_thread(client.show_user)
        instances = await asyncio.to_thread(client.show_instances)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}
    return {
        "ok": True,
        "balance": _number((user or {}).get("balance")),
        "total_spend": _number((user or {}).get("total_spend")),
        "username": (user or {}).get("username"),
        "instances": len(instances or []),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def test_offers(limit: int = 5) -> Dict[str, Any]:
    """Cari offer sesuai filter + allowlist + harga, tanpa membuat instance."""
    settings = get_settings()
    client = _client()
    query = (settings.VAST_GPU_FILTER or "").strip()
    try:
        offers = await asyncio.to_thread(
            client.search_offers, query, "on-demand", "dph_total+", 100
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mencari offer Vast: {exc}") from exc
    cap = float(settings.VAST_ONESHOT_MAX_PRICE or 0)
    allowlist = normalize_allowlist(settings.VAST_GPU_ALLOWLIST)

    def _key(name: Any) -> str:
        import re

        return re.sub(r"[^a-z0-9]", "", str(name or "").lower())

    allowed = {_key(name) for name in allowlist}
    usable: List[Dict[str, Any]] = []
    for offer in offers or []:
        price = _number(offer.get("dph_total")) or 0.0
        if not offer.get("rentable") or price <= 0:
            continue
        if cap > 0 and price > cap:
            continue
        if allowed and _key(offer.get("gpu_name")) not in allowed:
            continue
        usable.append(offer)
    usable.sort(key=lambda item: _number(item.get("dph_total")) or 0)
    selected = usable[: max(1, min(20, int(limit or 5)))]
    return {
        "filter": query,
        "max_price_per_hour": cap or None,
        "gpu_allowlist": allowlist,
        "total_matched": len(usable),
        "offers": [
            {
                "id": offer.get("id"),
                "gpu_name": offer.get("gpu_name"),
                "num_gpus": offer.get("num_gpus"),
                "gpu_ram": offer.get("gpu_ram"),
                "disk_space": offer.get("disk_space"),
                "inet_down": offer.get("inet_down"),
                "price_per_hour": _number(offer.get("dph_total")),
                "machine_id": offer.get("machine_id"),
            }
            for offer in selected
        ],
    }


def _is_secret(name: str) -> bool:
    upper = name.upper()
    return any(
        marker in upper
        for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL", "ENCRYPTION")
    )


def _mask(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return "****" + text[-4:] if len(text) > 4 else "****"


async def _local_costs(db) -> Dict[str, Any]:
    from sqlalchemy import select

    from app.models.worker_instance import WorkerInstance

    rows = (
        await db.execute(
            select(WorkerInstance).order_by(WorkerInstance.created_at.desc()).limit(500)
        )
    ).scalars().all()
    now = datetime.now(timezone.utc)
    total = 0.0
    by_day: Dict[str, float] = {}
    for row in rows:
        start = row.ready_at or row.created_at
        if not start:
            continue
        end = row.destroyed_at or now
        seconds = max(0.0, (end - start).total_seconds())
        cost = (_number(row.price_per_hour) or 0.0) * seconds / 3600
        total += cost
        day = start.date().isoformat()
        by_day[day] = by_day.get(day, 0.0) + cost
    return {
        "total_estimated": round(total, 4),
        "by_day": [
            {"date": day, "cost": round(cost, 4)}
            for day, cost in sorted(by_day.items(), reverse=True)[:30]
        ],
        "instances_sampled": len(rows),
    }


def _normalize_invoices(items: Optional[list]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "timestamp": _iso(item.get("timestamp")),
                "amount": _number(item.get("amount")),
                "type": str(item.get("type") or "")[:20],
                "description": str(item.get("description") or "")[:300],
                "instance_id": item.get("instance_id"),
                "quantity": _number(item.get("quantity")),
                "rate": _number(item.get("rate")),
            }
        )
    result.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
    return result


async def billing_summary(
    db,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    invoice_type: Optional[str] = None,
) -> Dict[str, Any]:
    client = _client()
    try:
        user = await asyncio.to_thread(client.show_user)
        raw = await asyncio.to_thread(
            client.show_invoices,
            start_date=start_date or None,
            end_date=end_date or None,
        )
    except Exception as exc:
        raise RuntimeError(f"Gagal mengambil billing Vast: {exc}") from exc
    invoices = _normalize_invoices(
        (raw or {}).get("invoices") if isinstance(raw, dict) else None
    )
    wanted = (invoice_type or "").strip().lower()
    if wanted:
        invoices = [row for row in invoices if row.get("type") == wanted]
    charges = sum(abs(row["amount"] or 0) for row in invoices if row.get("type") == "charge")
    credits = sum(abs(row["amount"] or 0) for row in invoices if row.get("type") == "credit")
    local = await _local_costs(db)
    return {
        "ok": True,
        "account": {
            "username": (user or {}).get("username"),
            "balance": _number((user or {}).get("balance")),
            "total_spend": _number((user or {}).get("total_spend")),
            "credit": _number((user or {}).get("credit")),
        },
        "summary": {
            "invoices": len(invoices),
            "charges": round(charges, 4),
            "credits": round(credits, 4),
            "net": round(charges - credits, 4),
        },
        "invoices": invoices[:200],
        "local": local,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def worker_env_spec() -> List[Dict[str, Any]]:
    """Daftar env worker (satu sumber dengan dispatch instance)."""
    env = build_worker_env()
    items: List[Dict[str, Any]] = [
        {
            "name": "CLIPZI_ROLE",
            "required": True,
            "runtime": True,
            "set": True,
            "secret": False,
            "preview": "worker (otomatis)",
        },
        {
            "name": "CLIPZI_TASK_ID",
            "required": True,
            "runtime": True,
            "set": True,
            "secret": False,
            "preview": "diisi otomatis per task",
        },
    ]
    for name in WORKER_ENV_REQUIRED + WORKER_ENV_OPTIONAL:
        value = env.get(name, "")
        secret = _is_secret(name)
        items.append(
            {
                "name": name,
                "required": name in WORKER_ENV_REQUIRED,
                "runtime": False,
                "set": bool(value),
                "secret": secret,
                "preview": (_mask(value) if secret else value[:80]) if value else "",
            }
        )
    return items


def env_text(reveal: bool = False) -> str:
    """Export .env worker; nilai secret disamarkan kecuali reveal=True (admin)."""
    env = build_worker_env()
    lines = ["# ClipziAI worker environment (auto-generated)"]
    for name in WORKER_ENV_REQUIRED + WORKER_ENV_OPTIONAL:
        value = env.get(name, "")
        if value and not reveal and _is_secret(name):
            value = "****"
        lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


async def sync_env_to_vast(
    keys: Optional[List[str]] = None, dry_run: bool = False
) -> Dict[str, Any]:
    """Buat/perbarui environment variable akun Vast dari env backend."""
    client = _client()
    try:
        existing = await asyncio.to_thread(client.show_env_vars, True)
    except TypeError:
        existing = await asyncio.to_thread(client.show_env_vars)
    except Exception as exc:
        raise RuntimeError(f"Gagal membaca env Vast: {exc}") from exc
    existing = existing if isinstance(existing, dict) else {}
    target = build_worker_env()
    selected = (
        list(target.keys()) if not keys else [name for name in keys if name in target]
    )

    results: List[Dict[str, Any]] = []
    for name in selected:
        if name in RESERVED_ENV:
            results.append({"name": name, "action": "skipped_reserved"})
            continue
        value = target.get(name)
        if not value:
            results.append({"name": name, "action": "skipped_empty"})
            continue
        if name not in existing:
            action = "create"
        elif str(existing.get(name)) != str(value):
            action = "update"
        else:
            action = "same"
        if action in ("create", "update") and not dry_run:
            try:
                call = client.create_env_var if action == "create" else client.update_env_var
                await asyncio.to_thread(call, name, value)
            except Exception as exc:
                results.append({"name": name, "action": "error", "error": str(exc)[:200]})
                continue
        results.append({"name": name, "action": action})

    summary: Dict[str, int] = {}
    for row in results:
        summary[row["action"]] = summary.get(row["action"], 0) + 1
    return {"dry_run": dry_run, "results": results, "summary": summary}
