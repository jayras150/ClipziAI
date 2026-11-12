"""
Setelan ekosistem platform + pergantian domain (satu sumber kebenaran di DB).

Alur ganti domain (opsi A — agent di VPS):
  1. Admin isi domain baru di dashboard -> `POST /api/admin/settings/platform/apply-domain`.
  2. Backend menyimpan `pending_domain` + status `pending` (bukan langsung
     mengubah server) dan mencatat audit.
  3. Agent di VPS (`deploy/clipzi-domain-sync.sh` + timer) membaca DB, menulis
     `DOMAIN`/`ADMIN_DOMAIN` ke `.env`, reload Caddy, opsional update DNS
     Cloudflare, lalu memanggil `POST /api/internal/domain-applied` (HMAC).
  4. Backend menandai `applied_domain` + status `applied`.

Kenapa tidak langsung menulis .env dari backend: container tidak punya akses
ke host. Cara ini tetap "1 klik" untuk admin, tapi tidak memberi backend akses
root ke VPS.
"""
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.platform_settings import get_setting, set_setting

PLATFORM_KEY = "platform"
CACHE_TTL_SECONDS = 60

DEFAULT_PLATFORM: Dict[str, Any] = {
    "site_url": "",
    "admin_url": "",
    "support_email": "",
    "timezone": "Asia/Jakarta",
    "maintenance_mode": False,
    "signup_enabled": True,
    "google_client_id": "",
    "pending_domain": None,
    "pending_admin_domain": None,
    "applied_domain": None,
    "domain_status": "idle",  # idle | pending | applied | failed
    "domain_requested_at": None,
    "domain_applied_at": None,
    "domain_last_error": None,
}

_cache: Dict[str, Any] = {}

# Origin tambahan untuk CORS (dipakai middleware dinamis di main.py).
# Diisi setiap kali setelan platform dimuat/disimpan, sehingga ganti domain
# langsung berlaku tanpa restart container.
EXTRA_ORIGINS: list[str] = []


def update_extra_origins(config: Dict[str, Any]) -> list[str]:
    global EXTRA_ORIGINS
    origins = []
    for key in ("site_url", "admin_url"):
        value = config.get(key)
        if value:
            origins.append(value)
    EXTRA_ORIGINS = origins
    return EXTRA_ORIGINS


def clear_cache() -> None:
    _cache.clear()


def normalize_url(value: Optional[str]) -> str:
    """Buang spasi + trailing slash; kosong -> ''."""
    return (value or "").strip().rstrip("/")


def validate_url(value: str, field: str = "URL") -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"{field} harus URL lengkap, contoh https://domain.com")
    return normalize_url(value)


def normalize_domain(value: Optional[str]) -> str:
    """Terima 'domain.com' atau 'https://domain.com/' -> 'domain.com'."""
    text = (value or "").strip()
    if not text:
        return ""
    if "://" in text:
        text = urlparse(text).netloc or text
    text = text.rstrip("/").lower()
    if "/" in text or " " in text:
        raise ValueError("Domain tidak valid (tanpa path/spasi), contoh admin.domain.com")
    return text


def normalize_platform(value: Optional[dict]) -> Dict[str, Any]:
    merged = dict(DEFAULT_PLATFORM)
    if isinstance(value, dict):
        merged.update({k: v for k, v in value.items() if k in DEFAULT_PLATFORM})

    merged["site_url"] = normalize_url(merged.get("site_url"))
    merged["admin_url"] = normalize_url(merged.get("admin_url"))
    merged["support_email"] = (merged.get("support_email") or "").strip()
    merged["timezone"] = (merged.get("timezone") or "Asia/Jakarta").strip()
    merged["google_client_id"] = (merged.get("google_client_id") or "").strip()
    merged["maintenance_mode"] = bool(merged.get("maintenance_mode"))
    merged["signup_enabled"] = bool(merged.get("signup_enabled", True))

    status = str(merged.get("domain_status") or "idle").lower()
    merged["domain_status"] = (
        status if status in ("idle", "pending", "applied", "failed") else "idle"
    )
    return merged


async def get_platform_config(db: AsyncSession) -> Dict[str, Any]:
    cached = _cache.get(PLATFORM_KEY)
    if cached and time.time() - cached["_ts"] < CACHE_TTL_SECONDS:
        return {k: v for k, v in cached.items() if k != "_ts"}
    raw = await get_setting(db, PLATFORM_KEY, None)
    config = normalize_platform(raw if isinstance(raw, dict) else None)
    _cache[PLATFORM_KEY] = {**config, "_ts": time.time()}
    return config


async def set_platform_config(db: AsyncSession, value: dict) -> Dict[str, Any]:
    merged = await get_platform_config(db)
    merged.update({k: v for k, v in (value or {}).items() if k in DEFAULT_PLATFORM})
    config = normalize_platform(merged)
    await set_setting(db, PLATFORM_KEY, config)
    clear_cache()
    return config


def site_url(config: Dict[str, Any]) -> str:
    """URL publik efektif (fallback ke FRONTEND_URL dari env)."""
    from app.core.config import get_settings

    return config.get("site_url") or get_settings().FRONTEND_URL.rstrip("/")


def admin_url(config: Dict[str, Any]) -> str:
    return config.get("admin_url") or ""


def apply_platform_config_to_env(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Terapkan setelan platform ke objek settings yang sedang hidup.

    Efek: link di email/YouTube (`FRONTEND_URL`) dan nilai default lain yang
    dibaca kode lain langsung memakai domain terbaru tanpa restart container.
    """
    from app.core.config import get_settings

    settings = get_settings()
    injected = []
    url = config.get("site_url")
    if url:
        settings.FRONTEND_URL = url
        injected.append("FRONTEND_URL")
    update_extra_origins(config)
    return {"injected": injected, "effective_site_url": site_url(config)}


async def load_and_apply_platform_config() -> Dict[str, Any]:
    """Dipanggil saat startup: muat setelan dari DB lalu terapkan ke env."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        config = await get_platform_config(db)
    apply_platform_config_to_env(config)
    return config
