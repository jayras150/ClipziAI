"""
Pool proxy untuk download YouTube: simpan, filter aktif, dan pakai otomatis.

Alur yang didukung dashboard:
  1. Upload banyak file .txt (atau paste) -> proxy_parser menormalkan.
  2. START FILTER ACTIVE PROXY -> tiap proxy diuji (ipify / YouTube 204).
     Hanya yang aktif disimpan; yang mati dibuang.
  3. Hasilnya digenerate menjadi SATU file `active_txt` (kanonik) yang otomatis
     dipakai sistem: settings.YTDLP_PROXY + env YTDLP_PROXY_POOL (untuk worker).

Data disimpan di platform_settings key `proxy_pool` supaya tidak perlu migrasi
tabel baru.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.platform_settings import get_setting, set_setting
from app.services.proxy_parser import mask_url, parse_proxy_text

PROXY_KEY = "proxy_pool"
CACHE_TTL = 30
DEFAULT_TARGET = "https://api.ipify.org?format=json"
YOUTUBE_CHECK = "https://www.youtube.com/generate_204"
MAX_KEEP = 500

DEFAULT_POOL: Dict[str, Any] = {
    "enabled": True,
    "auto_use": True,
    "rotation": "round_robin",
    "filter": {
        "target": DEFAULT_TARGET,
        "timeout_s": 8,
        "concurrency": 25,
        "check_youtube": True,
        "last_run": None,
        "tested": 0,
        "active": 0,
        "dead": 0,
    },
    "items": [],
    "active_txt": "",
    "updated_at": None,
}

_cache: Dict[str, Any] = {}
_job: Dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "total": 0,
    "tested": 0,
    "active": 0,
    "dead": 0,
    "error": None,
    "target": DEFAULT_TARGET,
}
_task: Optional[asyncio.Task] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clear_cache() -> None:
    _cache.clear()


def normalize_items(value: Any) -> List[Dict[str, Any]]:
    """Rapikan daftar item dari DB/UI menjadi bentuk konsisten."""
    items: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return items
    seen = set()
    for raw in value[:MAX_KEEP]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        status = str(raw.get("status") or "unchecked").lower()
        items.append(
            {
                "url": url,
                "label": (str(raw.get("label") or "").strip() or None),
                "scheme": str(raw.get("scheme") or url.split("://", 1)[0]),
                "status": status if status in ("active", "dead", "unchecked") else "unchecked",
                "latency_ms": raw.get("latency_ms"),
                "exit_ip": raw.get("exit_ip"),
                "last_checked": raw.get("last_checked"),
                "error": raw.get("error"),
                "fail_streak": int(raw.get("fail_streak") or 0),
            }
        )
    return items


def render_active_txt(items: List[Dict[str, Any]]) -> str:
    """Satu file txt berisi HANYA proxy aktif (format kanonik)."""
    lines = [item["url"] for item in items if item.get("status") == "active"]
    return "\n".join(lines) + ("\n" if lines else "")


def normalize_pool(value: Optional[dict]) -> Dict[str, Any]:
    merged = dict(DEFAULT_POOL)
    merged["filter"] = dict(DEFAULT_POOL["filter"])
    if isinstance(value, dict):
        for key, val in value.items():
            if key in ("filter", "items"):
                continue
            if key in merged:
                merged[key] = val
        if isinstance(value.get("filter"), dict):
            merged["filter"].update({k: v for k, v in value["filter"].items() if k in DEFAULT_POOL["filter"]})
    merged["items"] = normalize_items(value.get("items") if isinstance(value, dict) else None)
    merged["enabled"] = bool(merged.get("enabled", True))
    merged["auto_use"] = bool(merged.get("auto_use", True))
    merged["active_txt"] = render_active_txt(merged["items"])
    return merged


async def get_pool(db: AsyncSession) -> Dict[str, Any]:
    cached = _cache.get("pool")
    if cached and time.time() - cached["_ts"] < CACHE_TTL:
        return cached["value"]
    raw = await get_setting(db, PROXY_KEY, None)
    pool = normalize_pool(raw if isinstance(raw, dict) else None)
    _cache["pool"] = {"_ts": time.time(), "value": pool}
    return pool


async def set_pool(db: AsyncSession, payload: dict) -> Dict[str, Any]:
    current = await get_pool(db)
    merged = {**current, **(payload or {})}
    merged["updated_at"] = _now()
    pool = normalize_pool(merged)
    await set_setting(db, PROXY_KEY, pool)
    clear_cache()
    apply_pool_to_env(pool)
    return pool


def active_urls(pool: Dict[str, Any]) -> List[str]:
    return [item["url"] for item in pool.get("items", []) if item.get("status") == "active"]


def apply_pool_to_env(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Pakai otomatis: proxy aktif pertama + seluruh pool untuk rotasi worker."""
    settings = get_settings()
    urls = active_urls(pool) if pool.get("enabled", True) else []
    first = urls[0] if urls else None
    settings.YTDLP_PROXY = first
    if first:
        os.environ["YTDLP_PROXY"] = first
    else:
        os.environ.pop("YTDLP_PROXY", None)
    os.environ["YTDLP_PROXY_POOL"] = json.dumps(urls[:200])
    return {"proxy": mask_url(first) if first else None, "count": len(urls)}


async def load_and_apply_proxy_pool() -> Dict[str, Any]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        pool = await get_pool(db)
    apply_pool_to_env(pool)
    return pool

async def _test_proxy(
    url: str, target: str, timeout: float, check_youtube: bool
) -> Dict[str, Any]:
    """Uji satu proxy: ambil exit IP + latency, opsional cek YouTube."""
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(
            proxy=url, timeout=timeout, follow_redirects=True
        ) as client:
            response = await client.get(target)
            if response.status_code != 200:
                return {
                    "ok": False,
                    "error": "HTTP " + str(response.status_code),
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            exit_ip = None
            try:
                exit_ip = (response.json() or {}).get("ip")
            except Exception:
                exit_ip = (response.text or "").strip()[:45] or None

            if check_youtube:
                youtube = await client.get(YOUTUBE_CHECK)
                if youtube.status_code not in (204, 200):
                    return {
                        "ok": False,
                        "error": "youtube HTTP " + str(youtube.status_code),
                        "latency_ms": int((time.monotonic() - started) * 1000),
                        "exit_ip": exit_ip,
                    }

        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "exit_ip": exit_ip,
        }
    except Exception as exc:  # timeout, TLS, auth, dns, socks
        return {
            "ok": False,
            "error": (type(exc).__name__ + ": " + str(exc))[:140],
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


def job_status() -> Dict[str, Any]:
    return dict(_job)


def _set_job(**kwargs: Any) -> None:
    _job.update(kwargs)


async def _run_filter(
    items: List[Dict[str, Any]],
    target: str,
    timeout: float,
    concurrency: int,
    check_youtube: bool,
) -> None:
    from app.db.session import AsyncSessionLocal

    semaphore = asyncio.Semaphore(max(1, min(concurrency, 50)))
    results: List[Dict[str, Any]] = []
    lock = asyncio.Lock()

    async def worker(item: Dict[str, Any]) -> None:
        async with semaphore:
            outcome = await _test_proxy(item["url"], target, timeout, check_youtube)
        checked_at = _now()
        async with lock:
            results.append(
                {
                    **item,
                    "status": "active" if outcome.get("ok") else "dead",
                    "latency_ms": outcome.get("latency_ms"),
                    "exit_ip": outcome.get("exit_ip"),
                    "error": outcome.get("error"),
                    "last_checked": checked_at,
                    "fail_streak": 0 if outcome.get("ok") else item.get("fail_streak", 0) + 1,
                }
            )
            _set_job(
                tested=len(results),
                active=len([r for r in results if r["status"] == "active"]),
                dead=len([r for r in results if r["status"] == "dead"]),
            )

    await asyncio.gather(*(worker(item) for item in items))

    active = [r for r in results if r["status"] == "active"]
    active.sort(key=lambda row: row.get("latency_ms") or 10**9)
    # Yang mati dibuang; hanya proxy aktif yang disimpan (permintaan dashboard).
    active = active[:MAX_KEEP]

    async with AsyncSessionLocal() as db:
        pool = await get_pool(db)
        stats = {
            "target": target,
            "timeout_s": timeout,
            "concurrency": concurrency,
            "check_youtube": check_youtube,
            "last_run": _now(),
            "tested": len(results),
            "active": len(active),
            "dead": len(results) - len(active),
        }
        await set_pool(
            db,
            {"items": active, "filter": stats, "updated_at": _now()},
        )

    _set_job(status="done", finished_at=_now(), total=len(items))


async def start_filter(
    raw_text: Optional[str] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    target: str = DEFAULT_TARGET,
    timeout: float = 8.0,
    concurrency: int = 25,
    check_youtube: bool = True,
) -> Dict[str, Any]:
    """Mulai job filter di background (dipanggil tombol START FILTER)."""
    global _task
    if _task and not _task.done():
        return {"started": False, "status": _job, "message": "Filter masih berjalan"}

    candidates: List[Dict[str, Any]] = []
    if raw_text:
        parsed = parse_proxy_text(raw_text)
        candidates.extend(parsed["items"])
    if items:
        candidates.extend(normalize_items(items))

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)

    if not deduped:
        return {"started": False, "status": _job, "message": "Tidak ada proxy valid untuk diuji"}

    _set_job(
        status="running",
        started_at=_now(),
        finished_at=None,
        total=len(deduped),
        tested=0,
        active=0,
        dead=0,
        error=None,
        target=target,
    )
    _task = asyncio.create_task(
        _run_filter(deduped, target, timeout, concurrency, check_youtube)
    )
    return {"started": True, "total": len(deduped), "status": _job}
