"""Branding platform (nama, logo, favicon, warna) yang diatur admin."""
import re
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import PlatformSetting

BRANDING_KEY = "branding"
CACHE_TTL_SECONDS = 60

DEFAULT_BRANDING: Dict[str, Any] = {
    "app_name": "Clipzy AI",
    "tagline": "Turn long videos into viral shorts",
    "logo_url": None,
    "favicon_url": None,
    "og_image_url": None,
    "accent_color": "#f4c76b",
    "support_email": None,
    "footer_note": None,
}

_cache: Dict[str, tuple] = {}


def clear_cache() -> None:
    _cache.clear()


def _clean_text(value: Any, limit: int) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _clean_url(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if not text.startswith(("http://", "https://", "/")):
        return None
    return text[:500]


def normalize_branding(value: Optional[dict]) -> Dict[str, Any]:
    merged = dict(DEFAULT_BRANDING)
    if isinstance(value, dict):
        merged.update({k: v for k, v in value.items() if k in DEFAULT_BRANDING})

    merged["app_name"] = _clean_text(merged.get("app_name"), 60) or DEFAULT_BRANDING["app_name"]
    merged["tagline"] = _clean_text(merged.get("tagline"), 120)
    merged["footer_note"] = _clean_text(merged.get("footer_note"), 160)
    merged["support_email"] = _clean_text(merged.get("support_email"), 120)
    for field in ("logo_url", "favicon_url", "og_image_url"):
        merged[field] = _clean_url(merged.get(field))

    color = str(merged.get("accent_color") or DEFAULT_BRANDING["accent_color"]).strip()
    merged["accent_color"] = (
        color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else DEFAULT_BRANDING["accent_color"]
    )
    return merged


async def get_branding(db: AsyncSession) -> Dict[str, Any]:
    cached = _cache.get(BRANDING_KEY)
    if cached and time.time() - cached[0] <= CACHE_TTL_SECONDS:
        return dict(cached[1])
    result = await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == BRANDING_KEY)
    )
    row = result.scalar_one_or_none()
    config = normalize_branding(row.value if row and isinstance(row.value, dict) else None)
    _cache[BRANDING_KEY] = (time.time(), config)
    return dict(config)


async def set_branding(db: AsyncSession, payload: dict) -> Dict[str, Any]:
    current = await get_branding(db)
    merged = dict(current)
    merged.update({k: v for k, v in (payload or {}).items() if k in DEFAULT_BRANDING})
    config = normalize_branding(merged)

    result = await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == BRANDING_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(PlatformSetting(key=BRANDING_KEY, value=config))
    else:
        row.value = config
    await db.commit()
    clear_cache()
    return config
