"""Registry prompt AI yang bisa diubah admin (tanpa deploy ulang).

Prompt disimpan di `platform_settings` key `ai_prompts` sebagai
`{"<key>": "<template>"}`; hanya override yang disimpan, default ada di
`ai_prompt_defaults.py`. Worker memuat cache di awal task lewat `load_prompts()`
lalu memakai `get_sync()` (sinkron) di modul yang tidak async.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import PlatformSetting
from app.services.ai_prompt_defaults import (
    DEFAULT_PROMPTS,
    PROMPT_KEYS,
    PROMPT_META,
    SAMPLE_CONTEXT,
)

logger = logging.getLogger(__name__)

SETTING_KEY = "ai_prompts"
HISTORY_KEY = "ai_prompt_history"
CACHE_TTL_SECONDS = 60
HISTORY_LIMIT = 40

_cache: Dict[str, Any] = {"at": 0.0, "prompts": {}}


def clear_cache() -> None:
    _cache["at"] = 0.0
    _cache["prompts"] = {}


def _apply(template: str, ctx: Optional[Dict[str, Any]] = None) -> str:
    """Ganti `{{var}}` dengan nilai ctx; placeholder asing dibiarkan apa adanya."""
    values = {str(k): "" if v is None else str(v) for k, v in (ctx or {}).items()}
    return re.sub(
        r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}",
        lambda match: values.get(match.group(1), match.group(0)),
        template or "",
    )


def default_prompt(key: str) -> str:
    return DEFAULT_PROMPTS.get(key, "")


def get_sync(key: str, ctx: Optional[Dict[str, Any]] = None, fallback: str = "") -> str:
    """Ambil prompt dari cache proses (fallback ke default). Aman dipanggil sinkron."""
    prompts = _cache.get("prompts") or {}
    template = str(prompts.get(key) or DEFAULT_PROMPTS.get(key) or fallback)
    return _apply(template, ctx)


def _merge(stored: Optional[dict]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for key in PROMPT_KEYS:
        override = str((stored or {}).get(key) or "").strip()
        merged[key] = override or DEFAULT_PROMPTS[key]
    return merged


def _public(prompts: Dict[str, str], stored: Optional[dict]) -> Dict[str, Any]:
    stored = stored or {}
    return {
        "prompts": prompts,
        "overrides": {k: v for k, v in stored.items() if k in PROMPT_KEYS},
        "defaults": DEFAULT_PROMPTS,
        "meta": [
            {"key": key, **PROMPT_META.get(key, {}), "is_custom": bool(stored.get(key))}
            for key in PROMPT_KEYS
        ],
        "variables": {key: PROMPT_META.get(key, {}).get("variables", []) for key in PROMPT_KEYS},
        "sample_context": SAMPLE_CONTEXT,
    }


async def get_prompts(db: AsyncSession) -> Dict[str, Any]:
    row = (
        await db.execute(select(PlatformSetting).where(PlatformSetting.key == SETTING_KEY))
    ).scalar_one_or_none()
    stored = row.value if row is not None and isinstance(row.value, dict) else {}
    prompts = _merge(stored)
    _cache["prompts"] = dict(prompts)
    _cache["at"] = time.time()
    return _public(prompts, stored)


async def load_prompts() -> Dict[str, str]:
    # Dipakai worker/pipeline di awal task agar prompt terbaru terpakai.
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            data = await get_prompts(db)
        return data["prompts"]
    except Exception as exc:  # noqa: BLE001 - jangan pernah gagalkan task
        logger.warning("Gagal memuat prompt AI: %s", str(exc)[:200])
        return dict(DEFAULT_PROMPTS)


async def _append_history(db: AsyncSession, entries: List[Dict[str, Any]]) -> None:
    row = (
        await db.execute(select(PlatformSetting).where(PlatformSetting.key == HISTORY_KEY))
    ).scalar_one_or_none()
    current = row.value if row is not None and isinstance(row.value, list) else []
    merged = (entries + list(current))[:HISTORY_LIMIT]
    if row is None:
        db.add(PlatformSetting(key=HISTORY_KEY, value=cast(Any, merged)))
    else:
        row.value = cast(Any, merged)


async def get_history(db: AsyncSession) -> List[Dict[str, Any]]:
    row = (
        await db.execute(select(PlatformSetting).where(PlatformSetting.key == HISTORY_KEY))
    ).scalar_one_or_none()
    return list(row.value) if row is not None and isinstance(row.value, list) else []


async def save_prompt(
    db: AsyncSession,
    key: str,
    text: str,
    *,
    updated_by: str = "",
) -> Dict[str, Any]:
    if key not in PROMPT_KEYS:
        raise ValueError(f"Prompt tidak dikenal: {key}")
    row = (
        await db.execute(select(PlatformSetting).where(PlatformSetting.key == SETTING_KEY))
    ).scalar_one_or_none()
    stored = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    value = (text or "").strip()
    if value and value != DEFAULT_PROMPTS[key]:
        stored[key] = value[:20000]
    else:
        stored.pop(key, None)
    if row is None:
        db.add(PlatformSetting(key=SETTING_KEY, value=stored))
    else:
        row.value = stored
    await _append_history(
        db,
        [
            {
                "key": key,
                "at": datetime.now(timezone.utc).isoformat(),
                "by": updated_by,
                "action": "reset" if not value or value == DEFAULT_PROMPTS[key] else "update",
                "chars": len(value),
            }
        ],
    )
    await db.commit()
    clear_cache()
    return await get_prompts(db)


async def reset_prompt(db: AsyncSession, key: str, *, updated_by: str = "") -> Dict[str, Any]:
    return await save_prompt(db, key, "", updated_by=updated_by)


def preview(
    key: str,
    text: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
    prompts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    # Render pratinjau prompt dengan sample context (tanpa memanggil model).
    if key not in PROMPT_KEYS:
        raise ValueError(f"Prompt tidak dikenal: {key}")
    template = (
        str(text)
        if text is not None and str(text).strip()
        else str((prompts or {}).get(key) or DEFAULT_PROMPTS[key])
    )
    merged_ctx = {**SAMPLE_CONTEXT.get(key, {}), **(ctx or {})}
    return {
        "key": key,
        "rendered": _apply(template, merged_ctx),
        "template": template,
        "is_default": template.strip() == DEFAULT_PROMPTS[key].strip(),
    }


__all__ = [
    "DEFAULT_PROMPTS",
    "PROMPT_KEYS",
    "clear_cache",
    "default_prompt",
    "get_history",
    "get_prompts",
    "get_sync",
    "load_prompts",
    "preview",
    "reset_prompt",
    "save_prompt",
]
