"""Konfigurasi Vast.ai yang dapat diatur admin (DB > ENV > default).

Disimpan di `platform_settings` key `vast`; API key dienkripsi AES-256-GCM.
Nilai yang belum pernah disimpan di DB tetap mengikuti ENV `.env` sehingga
deployment lama tidak berubah sampai admin menekan Simpan.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.security import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

VAST_SETTING_KEY = "vast"

DEFAULT_VAST: Dict[str, Any] = {
    "dispatch_mode": "",
    "endpoint_url": "",
    "endpoint_name": "clipzi-processing",
    "worker_image": "",
    "template_hash": "",
    "worker_disk": 40,
    "gpu_filter": "gpu_ram>=16 disk_space>=40 inet_down>200",
    "gpu_allowlist": [],
    "max_price_per_hour": 0.0,
    "max_price_multiplier": 2.0,
    "min_workers": 0,
    "max_workers": 4,
    "target_util": 0.9,
    "inactivity_timeout": 300,
    "boot_timeout": 420,
    "worker_start_timeout": 120,
    "oneshot_timeout": 3600,
    "oneshot_boot_timeout": 900,
    "max_attempts": 5,
    "retry_backoff": 5,
    "request_timeout": 600,
    "supervisor_interval": 5,
    "api_key_enc": "",
}

FIELD_TO_ENV: Dict[str, str] = {
    "dispatch_mode": "VAST_DISPATCH_MODE",
    "endpoint_url": "VAST_ENDPOINT_URL",
    "endpoint_name": "VAST_ENDPOINT_NAME",
    "worker_image": "VAST_WORKER_IMAGE",
    "template_hash": "VAST_TEMPLATE_HASH",
    "worker_disk": "VAST_WORKER_DISK",
    "gpu_filter": "VAST_GPU_FILTER",
    "gpu_allowlist": "VAST_GPU_ALLOWLIST",
    "max_price_per_hour": "VAST_ONESHOT_MAX_PRICE",
    "max_price_multiplier": "VAST_MAX_PRICE_MULTIPLIER",
    "min_workers": "VAST_MIN_WORKERS",
    "max_workers": "VAST_MAX_WORKERS",
    "target_util": "VAST_TARGET_UTIL",
    "inactivity_timeout": "VAST_INACTIVITY_TIMEOUT",
    "boot_timeout": "VAST_BOOT_TIMEOUT",
    "worker_start_timeout": "VAST_WORKER_START_TIMEOUT",
    "oneshot_timeout": "VAST_ONESHOT_TIMEOUT",
    "oneshot_boot_timeout": "VAST_ONESHOT_BOOT_TIMEOUT",
    "max_attempts": "VAST_MAX_ATTEMPTS",
    "retry_backoff": "VAST_RETRY_BACKOFF",
    "request_timeout": "VAST_REQUEST_TIMEOUT",
    "supervisor_interval": "VAST_SUPERVISOR_INTERVAL",
}

_INT_RANGES = {
    "worker_disk": (10, 500),
    "min_workers": (0, 50),
    "max_workers": (1, 100),
    "inactivity_timeout": (30, 86400),
    "boot_timeout": (120, 3600),
    "worker_start_timeout": (30, 3600),
    "oneshot_timeout": (300, 86400),
    "oneshot_boot_timeout": (120, 3600),
    "max_attempts": (1, 20),
    "retry_backoff": (1, 300),
    "request_timeout": (30, 3600),
    "supervisor_interval": (2, 120),
}

_STR_FIELDS = (
    "endpoint_url",
    "endpoint_name",
    "worker_image",
    "template_hash",
    "gpu_filter",
)

_MODES = {"", "auto", "http", "sdk", "oneshot"}


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default
    return max(low, min(high, number))


def normalize_allowlist(value: Any) -> List[str]:
    """Terima list atau string koma; normalisasi nama GPU unik."""
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    seen: List[str] = []
    for raw in items:
        name = " ".join(str(raw or "").replace("_", " ").split())
        if not name:
            continue
        if name.lower() not in {item.lower() for item in seen}:
            seen.append(name[:60])
    return seen[:30]


def normalize_vast(raw: Optional[dict]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(DEFAULT_VAST)
    if isinstance(raw, dict):
        merged.update({key: value for key, value in raw.items() if key in DEFAULT_VAST})

    for field, (low, high) in _INT_RANGES.items():
        merged[field] = _clamp_int(merged.get(field), low, high, DEFAULT_VAST[field])

    for field, low, high in (
        ("max_price_per_hour", 0.0, 100.0),
        ("max_price_multiplier", 1.0, 10.0),
        ("target_util", 0.1, 1.0),
    ):
        try:
            number = float(merged.get(field))
        except (TypeError, ValueError):
            number = float(DEFAULT_VAST[field])
        merged[field] = round(max(low, min(high, number)), 3)

    mode = str(merged.get("dispatch_mode") or "").strip().lower()
    merged["dispatch_mode"] = mode if mode in _MODES else ""
    if mode == "auto":
        merged["dispatch_mode"] = ""

    for field in _STR_FIELDS:
        merged[field] = str(merged.get(field) or "").strip()[:400]

    merged["gpu_allowlist"] = normalize_allowlist(merged.get("gpu_allowlist"))
    merged["api_key_enc"] = str(merged.get("api_key_enc") or "")
    return merged


def _env_value(field: str) -> Any:
    attr = FIELD_TO_ENV.get(field)
    if not attr:
        return None
    value = getattr(get_settings(), attr, None)
    if field == "gpu_allowlist":
        return normalize_allowlist(value)
    return value


def _api_key(cfg: Dict[str, Any]) -> str:
    enc = str(cfg.get("api_key_enc") or "")
    if not enc:
        return ""
    try:
        return decrypt_field(enc).strip()
    except Exception:
        return ""


def mask_api_key(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return "****" + text[-4:] if len(text) > 4 else "****"


def validate_vast_key(value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    if text.lower().startswith(("http://", "https://")):
        raise ValueError("Yang diisi adalah URL, bukan API key Vast.")
    if any(char.isspace() for char in text):
        raise ValueError("API key Vast tidak boleh mengandung spasi/baris baru.")
    if len(text) < 32:
        raise ValueError("API key Vast terlalu pendek — sepertinya tidak lengkap.")


def validate_vast_config(cfg: Dict[str, Any]) -> None:
    mode = str(cfg.get("dispatch_mode") or "").lower()
    if mode not in _MODES:
        raise ValueError("Mode dispatch harus auto/http/sdk/oneshot.")
    url = str(cfg.get("endpoint_url") or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise ValueError("Endpoint URL harus dimulai dengan http:// atau https://.")
    image = str(cfg.get("worker_image") or "").strip()
    template = str(cfg.get("template_hash") or "").strip()
    if mode == "oneshot" and not image and not template:
        raise ValueError("Mode oneshot butuh worker image atau template hash.")


async def get_vast_config(db) -> Dict[str, Any]:
    """Konfigurasi efektif (DB > ENV > default) + sumber tiap field."""
    from app.services import platform_settings as ps

    stored = await ps.get_setting(db, VAST_SETTING_KEY, None)
    stored = stored if isinstance(stored, dict) else None
    cfg: Dict[str, Any] = dict(DEFAULT_VAST)
    sources: Dict[str, str] = {}

    for field in DEFAULT_VAST:
        if field == "api_key_enc":
            continue
        env_value = _env_value(field)
        if env_value not in (None, "", []):
            cfg[field] = env_value
            sources[field] = "env"
        else:
            sources[field] = "default"

    if stored:
        for field in DEFAULT_VAST:
            if field == "api_key_enc":
                continue
            value = stored.get(field)
            if value not in (None, "", []):
                cfg[field] = value
                sources[field] = "db"

    key = ""
    key_source = "none"
    if stored and stored.get("api_key_enc"):
        try:
            key = decrypt_field(stored["api_key_enc"]).strip()
            key_source = "db" if key else "db-error"
        except Exception:
            key = ""
            key_source = "db-error"
    if not key:
        env_key = (get_settings().VAST_API_KEY or "").strip()
        if env_key:
            key = env_key
            key_source = "env"

    cfg["api_key_enc"] = encrypt_field(key) if key else ""
    cfg = normalize_vast(cfg)
    cfg["_sources"] = sources
    cfg["_api_key_source"] = key_source
    return cfg


def effective_dispatch_mode(cfg: Dict[str, Any]) -> str:
    forced = str(cfg.get("dispatch_mode") or "").strip().lower()
    if forced:
        return forced
    if str(cfg.get("endpoint_url") or "").strip():
        return "http"
    if _api_key(cfg) and str(cfg.get("endpoint_name") or "").strip():
        return "sdk"
    return "oneshot"


def public_vast_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    key = _api_key(cfg)
    payload = {
        field: cfg.get(field)
        for field in DEFAULT_VAST
        if field != "api_key_enc"
    }
    payload.update(
        {
            "api_key_set": bool(key),
            "api_key_masked": mask_api_key(key),
            "api_key_source": cfg.get("_api_key_source") or "none",
            "sources": cfg.get("_sources") or {},
            "dispatch_mode_effective": effective_dispatch_mode(cfg),
            "ready": bool(key) and bool(cfg.get("worker_image") or cfg.get("template_hash")),
            "gpu_allowlist": normalize_allowlist(cfg.get("gpu_allowlist")),
        }
    )
    return payload


async def save_vast_config(db, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simpan perubahan admin, enkripsi key baru, lalu terapkan tanpa restart."""
    from app.services import platform_settings as ps

    current = await get_vast_config(db)
    merged: Dict[str, Any] = {field: current.get(field) for field in DEFAULT_VAST}

    for field in DEFAULT_VAST:
        if field == "api_key_enc":
            continue
        if field in payload and payload[field] is not None:
            merged[field] = payload[field]

    clear_key = bool(payload.get("clear_api_key"))
    new_key = str(payload.get("api_key") or "").strip()
    if new_key:
        validate_vast_key(new_key)
        merged["api_key_enc"] = encrypt_field(new_key)
    elif clear_key:
        merged["api_key_enc"] = ""
    else:
        merged["api_key_enc"] = current.get("api_key_enc") or ""

    validate_vast_config(merged)
    merged = normalize_vast(merged)

    stored = {field: merged[field] for field in DEFAULT_VAST}
    # Jangan membekukan key ENV ke DB bila admin tidak mengganti key.
    if not new_key and not clear_key and current.get("_api_key_source") != "db":
        stored["api_key_enc"] = ""
    await ps.set_setting(db, VAST_SETTING_KEY, stored)
    # Resolve ulang agar tombol "hapus key" kembali memakai ENV (bukan kosong).
    fresh = await get_vast_config(db)
    apply_vast_config(fresh)
    return fresh


async def reset_vast_config(db) -> Dict[str, Any]:
    """Hapus override DB; semua nilai kembali mengikuti ENV/default."""
    from app.services import platform_settings as ps

    await ps.set_setting(db, VAST_SETTING_KEY, {})
    cfg = await get_vast_config(db)
    apply_vast_config(cfg)
    return cfg


def apply_vast_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Terapkan konfigurasi ke objek settings yang hidup + reset cache Vast."""
    settings = get_settings()
    for field, attr in FIELD_TO_ENV.items():
        value = cfg.get(field)
        if field == "gpu_allowlist":
            value = ",".join(normalize_allowlist(value))
        try:
            setattr(settings, attr, value)
            os.environ[attr] = str(value if value is not None else "")
        except Exception as exc:  # pragma: no cover
            logger.warning("Gagal set %s: %s", attr, exc)

    key = _api_key(cfg)
    try:
        settings.VAST_API_KEY = key
        os.environ["VAST_API_KEY"] = key
    except Exception as exc:  # pragma: no cover
        logger.warning("Gagal set VAST_API_KEY: %s", exc)

    try:
        from app.services import vast_worker

        vast_worker._vast_client = None
        vast_worker._sdk_client = None
    except Exception:  # pragma: no cover
        pass
    return {
        "api_key_set": bool(key),
        "dispatch_mode": effective_dispatch_mode(cfg),
        "max_workers": cfg.get("max_workers"),
        "worker_disk": cfg.get("worker_disk"),
    }


async def load_and_apply_vast_config() -> Dict[str, Any]:
    """Dipanggil saat startup API agar setelan DB langsung berlaku."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cfg = await get_vast_config(db)
    apply_vast_config(cfg)
    return cfg
