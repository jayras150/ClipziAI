"""Konfigurasi AI yang dapat diatur admin dari dashboard.

"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.platform_setting import PlatformSetting
from app.services.ai_client import PROVIDER_DEFAULTS

logger = logging.getLogger(__name__)

AI_SETTING_KEY = "ai"
CACHE_TTL_SECONDS = 60

DEFAULT_AI: Dict[str, Any] = {
    "enabled": True,
    "provider": "openrouter",
    "base_url": "",
    "api_key_enc": "",
    "model_metadata": "openai/gpt-4o-mini",
    "model_rerank": "openai/gpt-4o-mini",
    "model_regenerate": "openai/gpt-6-luna",
    "temperature": 0.7,
    "max_tokens": 2048,
    "timeout_seconds": 90,
    "max_retries": 1,
    "rerank_enabled": True,
    "metadata_enabled": True,
    "rerank_budget_seconds": 120,
    "metadata_budget_seconds": 180,
    # Multi-endpoint: admin bisa mendaftar beberapa endpoint (provider + key +
    # model) dan memilih mana yang dipakai untuk metadata / rerank / regenerate.
    "endpoints": [],
    "endpoint_routes": {"metadata": "", "rerank": "", "regenerate": ""},
}

_INT_FIELDS = {
    "timeout_seconds",
    "max_tokens",
    "max_retries",
    "rerank_budget_seconds",
    "metadata_budget_seconds",
}

_cache: Dict[str, tuple] = {}


def clear_cache() -> None:
    _cache.clear()


def _fernet() -> Fernet:
    settings = get_settings()
    secret = (
        getattr(settings, "AI_SETTINGS_SECRET", None) or settings.SECRET_KEY or "clipzi"
    ).encode("utf-8")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def encrypt_api_key(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_api_key(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return text
    except Exception:
        return ""


def mask_api_key(value: str) -> str:
    text = value or ""
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return text[:4] + "..." + text[-4:]


def normalize_ai(value: Optional[dict]) -> Dict[str, Any]:
    merged = dict(DEFAULT_AI)
    if isinstance(value, dict):
        merged.update({k: v for k, v in value.items() if k in DEFAULT_AI})

    provider = str(merged.get("provider") or "openrouter").strip().lower()
    merged["provider"] = provider if provider in PROVIDER_DEFAULTS else "custom"
    merged["enabled"] = bool(merged.get("enabled"))
    merged["rerank_enabled"] = bool(merged.get("rerank_enabled"))
    merged["metadata_enabled"] = bool(merged.get("metadata_enabled"))

    base_url = str(merged.get("base_url") or "").strip()
    merged["base_url"] = base_url if base_url.startswith("http") else ""

    for field, low, high, default in (
        ("temperature", 0.0, 1.5, 0.7),
        ("timeout_seconds", 10, 300, 90),
        ("max_tokens", 128, 8192, 2048),
        ("max_retries", 0, 3, 1),
        ("rerank_budget_seconds", 20, 600, 120),
        ("metadata_budget_seconds", 20, 900, 180),
    ):
        raw_value = merged.get(field)
        if raw_value is None:
            number = float(default)
        else:
            try:
                number = float(raw_value)
            except (TypeError, ValueError):
                number = float(default)
        number = max(float(low), min(float(high), number))
        merged[field] = int(number) if field in _INT_FIELDS else round(number, 2)

    for field, default in (
        ("model_metadata", "openai/gpt-4o-mini"),
        ("model_rerank", "openai/gpt-4o-mini"),
        ("model_regenerate", "openai/gpt-6-luna"),
    ):
        text = str(merged.get(field) or "").strip()
        merged[field] = text[:120] or default

    merged["api_key_enc"] = str(merged.get("api_key_enc") or "")
    _normalize_endpoints(merged)
    return merged


def _normalize_endpoints(cfg: Dict[str, Any]) -> None:
    """Rapikan daftar endpoint AI (maks 6) + rute per fitur."""
    raw_items = cfg.get("endpoints")
    items: List[Dict[str, Any]] = []
    if isinstance(raw_items, list):
        for item in raw_items[:6]:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider") or "openrouter").strip().lower()
            if provider not in PROVIDER_DEFAULTS:
                provider = "custom"
            base_url = str(item.get("base_url") or "").strip()
            endpoint_id = str(item.get("id") or "").strip()[:40] or (
                f"{provider}-{len(items) + 1}"
            )
            items.append(
                {
                    "id": endpoint_id,
                    "label": str(item.get("label") or endpoint_id)[:60],
                    "provider": provider,
                    "base_url": base_url if base_url.startswith("http") else "",
                    "api_key_enc": str(item.get("api_key_enc") or ""),
                    "model_metadata": str(item.get("model_metadata") or "").strip()[:120],
                    "model_rerank": str(item.get("model_rerank") or "").strip()[:120],
                    "model_regenerate": str(item.get("model_regenerate") or "").strip()[:120],
                    "weight": max(1, min(1000, int(item.get("weight") or 100))),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
    cfg["endpoints"] = items
    ids = {item["id"] for item in items}
    routes = cfg.get("endpoint_routes")
    routes = routes if isinstance(routes, dict) else {}
    cfg["endpoint_routes"] = {
        feature: (str(routes.get(feature) or "") if str(routes.get(feature) or "") in ids else "")
        for feature in ("metadata", "rerank", "regenerate")
    }


def resolve_endpoint(cfg: Dict[str, Any], feature: str) -> Optional[Dict[str, Any]]:
    """Endpoint pilihan untuk `feature` (metadata/rerank/regenerate).

    Urutan: rute eksplisit -> endpoint aktif dengan bobot tertinggi -> None
    (pakai konfigurasi global seperti sebelumnya).
    """
    items = [i for i in (cfg.get("endpoints") or []) if i.get("enabled")]
    if not items:
        return None
    route_id = str((cfg.get("endpoint_routes") or {}).get(feature) or "")
    chosen = next((item for item in items if item["id"] == route_id), None)
    if chosen is None:
        chosen = max(items, key=lambda item: int(item.get("weight") or 0))
    defaults = PROVIDER_DEFAULTS.get(chosen["provider"], PROVIDER_DEFAULTS["custom"])
    key = decrypt_api_key(chosen.get("api_key_enc"))
    base_url = chosen.get("base_url") or defaults.get("base_url") or ""
    return {
        "id": chosen["id"],
        "label": chosen.get("label") or chosen["id"],
        "provider": chosen["provider"],
        "base_url": base_url,
        "api_key": key,
        "has_key": bool(key),
        "model_metadata": chosen.get("model_metadata")
        or cfg.get("model_metadata")
        or defaults.get("model"),
        "model_rerank": chosen.get("model_rerank")
        or cfg.get("model_rerank")
        or defaults.get("model"),
        "model_regenerate": chosen.get("model_regenerate")
        or cfg.get("model_regenerate")
        or defaults.get("model"),
    }


def effective_base_url(cfg: Dict[str, Any]) -> Optional[str]:
    provider = str(cfg.get("provider") or "openrouter")
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    return cfg.get("base_url") or defaults.get("base_url") or None


def ai_is_configured(cfg: Dict[str, Any]) -> bool:
    if not cfg.get("enabled"):
        return False
    try:
        key = decrypt_api_key(cfg.get("api_key_enc"))
    except Exception:
        return False
    if key:
        try:
            # Key yang isinya Base URL / terlalu pendek tidak dianggap siap.
            validate_api_key(key, str(cfg.get("provider") or ""))
        except ValueError:
            return False
        return True
    return cfg.get("provider") == "ollama" and bool(effective_base_url(cfg))


def validate_api_key(value: str, provider: str = "") -> None:
    """Tolak nilai yang jelas bukan API key (mis. Base URL yang salah tempel).

    Kasus nyata: kolom API key diisi `https://openrouter.ai/api/v1`, sehingga
    provider membalas 401 "Missing Authentication header" dan pesan lama
    ("AI belum aktif atau API key kosong") menyesatkan.
    """
    text = (value or "").strip()
    if not text:
        return
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        raise ValueError(
            "Yang diisi adalah Base URL, bukan API key. Tempel API key provider "
            "(contoh OpenRouter: sk-or-v1-...)."
        )
    if any(ch.isspace() for ch in text):
        raise ValueError("API key tidak boleh mengandung spasi/baris baru.")
    if len(text) < 16:
        raise ValueError("API key terlalu pendek — sepertinya tidak lengkap.")
    if provider and provider != "custom" and lowered.startswith("bearer "):
        raise ValueError("Hapus awalan 'Bearer ' — cukup key-nya saja.")


def ai_status_hint(cfg: Dict[str, Any]) -> Optional[str]:
    """Penjelasan singkat kenapa AI tidak siap dipakai (None bila siap).

    Pesan lama "AI belum aktif atau API key kosong" ambigu: sering kali key
    sudah benar tetapi toggle "AI aktif" mati. Dipakai endpoint admin & UI.
    """
    key = ""
    try:
        key = decrypt_api_key(cfg.get("api_key_enc"))
    except Exception as exc:
        return (
            "API key tersimpan tetapi tidak bisa didekripsi "
            f"({type(exc).__name__}). Simpan ulang API key."
        )
    if key.strip().lower().startswith(("http://", "https://")):
        return (
            "Nilai di kolom API key adalah Base URL, bukan API key. Ganti dengan "
            "API key provider (contoh OpenRouter: sk-or-v1-...)."
        )
    if not cfg.get("enabled") and key:
        return "AI dinonaktifkan (toggle 'AI aktif' mati). Aktifkan lalu uji lagi."
    if not cfg.get("enabled"):
        return "AI dinonaktifkan. Aktifkan toggle 'AI aktif' di Settings › AI."
    if not key and cfg.get("provider") != "ollama":
        return "API key kosong. Simpan API key provider terlebih dahulu."
    return None


def public_ai_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    key = decrypt_api_key(cfg.get("api_key_enc"))
    payload = {k: v for k, v in cfg.items() if k != "api_key_enc"}
    payload["api_key_set"] = bool(key)
    payload["api_key_masked"] = mask_api_key(key)
    payload["effective_base_url"] = effective_base_url(cfg)
    payload["providers"] = sorted(PROVIDER_DEFAULTS.keys())
    endpoints = []
    for item in cfg.get("endpoints") or []:
        endpoint_key = decrypt_api_key(item.get("api_key_enc"))
        endpoints.append(
            {
                **{k: v for k, v in item.items() if k != "api_key_enc"},
                "api_key_set": bool(endpoint_key),
                "api_key_masked": mask_api_key(endpoint_key),
            }
        )
    payload["endpoints"] = endpoints
    payload["active_endpoints"] = {
        feature: (resolve_endpoint(cfg, feature) or {}).get("id", "")
        for feature in ("metadata", "rerank", "regenerate")
    }
    # Alasan siap/tidaknya AI (None = siap). Ditampilkan sebagai banner di UI.
    payload["status_hint"] = ai_status_hint(cfg)
    payload["ready"] = ai_is_configured(cfg)
    return payload


async def _read_setting(db: AsyncSession) -> Optional[dict]:
    result = await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == AI_SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    return row.value if row and isinstance(row.value, dict) else None


async def get_ai_config(db: AsyncSession) -> Dict[str, Any]:
    cached = _cache.get(AI_SETTING_KEY)
    if cached and time.time() - cached[0] <= CACHE_TTL_SECONDS:
        return dict(cached[1])
    value = await _read_setting(db)
    cfg = normalize_ai(value)
    if value is None:
        settings = get_settings()
        cfg["provider"] = (settings.AI_PROVIDER or cfg["provider"]).strip().lower()
        if cfg["provider"] not in PROVIDER_DEFAULTS:
            cfg["provider"] = "custom"
        cfg["base_url"] = (settings.AI_BASE_URL or "").strip()
        cfg["api_key_enc"] = encrypt_api_key(
            settings.AI_API_KEY or settings.OPENAI_API_KEY or ""
        )
        cfg["model_metadata"] = settings.AI_MODEL or cfg["model_metadata"]
        cfg["model_rerank"] = settings.AI_MODEL or cfg["model_rerank"]
        cfg["model_regenerate"] = settings.AI_REGENERATE_MODEL or cfg["model_regenerate"]
        cfg["temperature"] = float(settings.AI_TEMPERATURE or cfg["temperature"])
        cfg["max_tokens"] = int(settings.AI_MAX_TOKENS or cfg["max_tokens"])
        cfg = normalize_ai(cfg)
    _cache[AI_SETTING_KEY] = (time.time(), cfg)
    return dict(cfg)


async def set_ai_config(db: AsyncSession, payload: dict) -> Dict[str, Any]:
    current = await get_ai_config(db)
    merged = dict(current)

    for field in DEFAULT_AI:
        if field in payload and payload[field] is not None:
            merged[field] = payload[field]
    if payload.get("clear_api_key"):
        merged["api_key_enc"] = ""
    if isinstance(payload.get("endpoints"), list):
        current_map = {item["id"]: item for item in current.get("endpoints") or []}
        stored_endpoints: List[Dict[str, Any]] = []
        for index, item in enumerate(payload["endpoints"][:6], 1):
            if not isinstance(item, dict):
                continue
            endpoint_id = str(item.get("id") or "").strip()[:40] or f"ep-{index}"
            previous = current_map.get(endpoint_id) or {}
            endpoint_key = str(item.get("api_key") or "").strip()
            if endpoint_key:
                validate_api_key(endpoint_key, str(item.get("provider") or ""))
            encrypted = (
                encrypt_api_key(endpoint_key)
                if endpoint_key
                else str(previous.get("api_key_enc") or item.get("api_key_enc") or "")
            )
            stored_endpoints.append(
                {**{k: v for k, v in item.items() if k != "api_key"}, "id": endpoint_id, "api_key_enc": encrypted}
            )
        merged["endpoints"] = stored_endpoints

    new_key = str(payload.get("api_key") or "").strip()
    if new_key:
        validate_api_key(new_key, str(merged.get("provider") or ""))
        merged["api_key_enc"] = encrypt_api_key(new_key)
        # Menyimpan API key = niat mengaktifkan AI. Tanpa ini, toggle "AI aktif"
        # yang pernah dimatikan membuat semua request gagal dengan pesan
        # "AI belum aktif atau API key kosong" walau key sudah benar.
        if payload.get("enabled") is None:
            merged["enabled"] = True

    cfg = normalize_ai(merged)

    result = await db.execute(
        select(PlatformSetting).where(PlatformSetting.key == AI_SETTING_KEY)
    )
    row = result.scalar_one_or_none()
    if row is None:
        db.add(PlatformSetting(key=AI_SETTING_KEY, value=cfg))
    else:
        row.value = cfg
    await db.commit()

    clear_cache()
    apply_ai_config_to_env(cfg)
    return cfg


def apply_ai_config_to_env(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Inject kredensial AI ke environment proses + objek settings yang hidup."""
    settings = get_settings()
    key = decrypt_api_key(cfg.get("api_key_enc"))
    values: Dict[str, Any] = {
        "AI_PROVIDER": cfg["provider"],
        "AI_API_KEY": key,
        "AI_BASE_URL": cfg.get("base_url") or "",
        "AI_MODEL": cfg["model_metadata"],
        "AI_TEMPERATURE": float(cfg["temperature"]),
        "AI_MAX_TOKENS": int(cfg["max_tokens"]),
        "AI_REGENERATE_MODEL": cfg["model_regenerate"],
        "AI_RERANK_MODEL": cfg["model_rerank"],
    }
    injected = []
    for name, value in values.items():
        os.environ[name] = value if isinstance(value, str) else str(value)
        try:
            setattr(settings, name, value)
            injected.append(name)
        except Exception as exc:
            logger.warning("Gagal set %s pada settings: %s", name, exc)
    return {
        "injected": injected,
        "provider": cfg["provider"],
        "base_url": effective_base_url(cfg),
        "api_key_set": bool(key),
    }


async def load_and_apply_ai_config() -> Dict[str, Any]:
    """Dipakai worker (tanpa request DB session) di awal setiap task."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cfg = await get_ai_config(db)
    apply_ai_config_to_env(cfg)
    return cfg
