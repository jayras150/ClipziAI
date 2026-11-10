"""
Setelan platform (key/value) + konfigurasi watermark.

Kenapa ada cache: pipeline memanggil `get_watermark_config()` untuk SETIAP klip.
Query DB tiap klip itu boros, jadi hasilnya di-cache singkat (60 detik) dan
cache dibersihkan setiap kali admin menyimpan setelan baru.
"""
import time
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_setting import PlatformSetting

WATERMARK_KEY = "watermark"
CACHE_TTL_SECONDS = 60

# Posisi yang didukung overlay_image/drawtext.
POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
# Plan yang bisa diatur admin (sesuai PlanType).
PLANS = ("free", "standar", "pro", "team")

DEFAULT_WATERMARK: Dict[str, Any] = {
    "enabled": False,
    "plans": ["free"],
    "image_url": None,
    "text": "clipzy.ai",
    "position": "bottom-right",
    "opacity": 0.85,
    "scale": 0.18,
    "text_color": "#ffffff",
    "margin": 40,
}

_cache: Dict[str, tuple[float, Any]] = {}


def clear_cache() -> None:
    _cache.clear()


def normalize_watermark(value: Optional[dict]) -> Dict[str, Any]:
    """Gabungkan nilai tersimpan dengan default + rapikan tipe/rentangnya."""
    merged = dict(DEFAULT_WATERMARK)
    if isinstance(value, dict):
        merged.update({k: v for k, v in value.items() if k in DEFAULT_WATERMARK})

    plans = merged.get("plans")
    if not isinstance(plans, list):
        plans = ["free"]
    merged["plans"] = [str(p).lower() for p in plans if str(p).lower() in PLANS] or ["free"]

    position = str(merged.get("position") or "bottom-right").lower()
    merged["position"] = position if position in POSITIONS else "bottom-right"

    try:
        merged["opacity"] = min(1.0, max(0.1, float(merged.get("opacity") or 0.85)))
    except (TypeError, ValueError):
        merged["opacity"] = 0.85
    try:
        merged["scale"] = min(0.6, max(0.05, float(merged.get("scale") or 0.18)))
    except (TypeError, ValueError):
        merged["scale"] = 0.18
    try:
        merged["margin"] = min(200, max(0, int(merged.get("margin") or 40)))
    except (TypeError, ValueError):
        merged["margin"] = 40

    merged["enabled"] = bool(merged.get("enabled"))
    image_url = merged.get("image_url")
    merged["image_url"] = str(image_url).strip() if image_url else None
    text = merged.get("text")
    merged["text"] = str(text).strip()[:60] if text else None
    color = str(merged.get("text_color") or "#ffffff").strip()
    merged["text_color"] = color if color.startswith("#") and len(color) == 7 else "#ffffff"
    return merged


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default


async def set_setting(db: AsyncSession, key: str, value: Any) -> Any:
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        row = PlatformSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    clear_cache()
    return value


def _cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if not entry:
        return None
    stamp, value = entry
    if time.time() - stamp > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return value


async def get_watermark_config(db: AsyncSession) -> Dict[str, Any]:
    """Konfigurasi watermark aktif (default aman: nonaktif)."""
    cached = _cache_get(WATERMARK_KEY)
    if cached is not None:
        return cached
    value = await get_setting(db, WATERMARK_KEY, None)
    config = normalize_watermark(value if isinstance(value, dict) else None)
    _cache[WATERMARK_KEY] = (time.time(), config)
    return config


async def set_watermark_config(db: AsyncSession, value: dict) -> Dict[str, Any]:
    config = normalize_watermark(value)
    await set_setting(db, WATERMARK_KEY, config)
    return config


def plan_is_watermarked(plan: Optional[str], config: Dict[str, Any]) -> bool:
    """True bila plan user termasuk sasaran watermark."""
    if not config.get("enabled"):
        return False
    plans = [str(p).lower() for p in (config.get("plans") or [])]
    return str(plan or "free").lower() in plans
