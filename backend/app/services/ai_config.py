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
    "model_transcribe": "openai/whisper-1",
    # Endpoint per kemampuan. Kosong = ikut base URL provider (lihat DEFAULT_PATHS).
    "endpoint_chat": "",
    "endpoint_transcribe": "",
    "endpoint_rerank": "",
    "temperature": 0.7,
    "max_tokens": 2048,
    "timeout_seconds": 90,
    "max_retries": 1,
    "rerank_enabled": True,
    "metadata_enabled": True,
    "rerank_budget_seconds": 120,
    "metadata_budget_seconds": 180,
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
    _normalize_capabilities(merged)
    return merged


CAPABILITY_ENDPOINT_FIELDS = {
    "chat": "endpoint_chat",
    "transcribe": "endpoint_transcribe",
    "rerank": "endpoint_rerank",
}
CAPABILITY_DEFAULT_PATHS = {
    "chat": "/chat/completions",
    "transcribe": "/audio/transcriptions",
    "rerank": "/rerank",
}
CAPABILITY_MODEL_FIELDS = {
    "chat": "model_metadata",
    "regenerate": "model_regenerate",
    "transcribe": "model_transcribe",
    "rerank": "model_rerank",
}


def _normalize_capabilities(cfg: Dict[str, Any]) -> None:
    """Rapikan endpoint per kemampuan (chat / transcribe / rerank)."""
    for field in CAPABILITY_ENDPOINT_FIELDS.values():
        value = str(cfg.get(field) or "").strip()
        cfg[field] = value if value.lower().startswith(("http://", "https://")) else ""
    cfg["model_transcribe"] = str(cfg.get("model_transcribe") or "").strip()[:120]


def resolve_capability(cfg: Dict[str, Any], capability: str) -> Dict[str, Any]:
    """URL + model + key untuk satu kemampuan, memakai SATU API key provider."""
    capability = capability if capability in CAPABILITY_MODEL_FIELDS else "chat"
    base = (effective_base_url(cfg) or "").rstrip("/")
    endpoint = str(cfg.get(CAPABILITY_ENDPOINT_FIELDS.get(capability, "endpoint_chat")) or "").strip()
    if not endpoint:
        path = CAPABILITY_DEFAULT_PATHS.get(capability, "/chat/completions")
        endpoint = f"{base}{path}" if base else ""
    model = str(cfg.get(CAPABILITY_MODEL_FIELDS[capability]) or "").strip()
    key = decrypt_api_key(cfg.get("api_key_enc"))
    return {
        "capability": capability,
        "url": endpoint,
        "base_url": base or None,
        "model": model,
        "has_key": bool(key),
        "ready": bool(endpoint) and (bool(key) or capability == "chat"),
    }


def resolve_endpoint(cfg: Dict[str, Any], feature: str) -> Optional[Dict[str, Any]]:
    """Legacy shim: routing sekarang per kemampuan (resolve_capability)."""
    return None


_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/audio/transcriptions",
    "/embeddings",
    "/rerank",
    "/completions",
)


def _strip_endpoint_path(url: str) -> str:
    """`https://host/v1/chat/completions` -> `https://host/v1`."""
    text = (url or "").strip().rstrip("/")
    for suffix in _ENDPOINT_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def effective_base_url(cfg: Dict[str, Any]) -> Optional[str]:
    """Base URL efektif untuk SDK OpenAI-compatible.

    Urutan: base_url eksplisit -> default provider -> turunan endpoint per
    kemampuan -> deteksi dari prefix API key. Kasus nyata yang diperbaiki:
    admin memakai provider `custom` dengan `base_url` kosong tapi
    `endpoint_chat=https://openrouter.ai/api/v1/`; tanpa penurunan ini SDK jatuh
    ke default OpenAI (api.openai.com) sehingga key OpenRouter ditolak 401 dan
    request regenerate metadata menggantung sampai Cloudflare 520.
    """
    provider = str(cfg.get("provider") or "openrouter")
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])
    configured = str(cfg.get("base_url") or "").strip().rstrip("/")
    if configured:
        return configured

    default_base = str(defaults.get("base_url") or "").strip().rstrip("/")
    try:
        key = decrypt_api_key(cfg.get("api_key_enc"))
    except Exception:  # noqa: BLE001
        key = ""

    # Key OpenRouter selalu ditolak bila dikirim ke api.openai.com.
    if key.startswith("sk-or-v1") and (not default_base or provider in ("custom", "openai")):
        return "https://openrouter.ai/api/v1"

    if not default_base:
        for field in ("endpoint_chat", "endpoint_transcribe", "endpoint_rerank"):
            value = str(cfg.get(field) or "").strip()
            if value.lower().startswith(("http://", "https://")):
                return _strip_endpoint_path(value)
    return default_base or None


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
    payload["capabilities"] = {
        name: resolve_capability(cfg, name)
        for name in ("chat", "regenerate", "transcribe", "rerank")
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
        # Wajib base URL efektif (bukan cfg["base_url"] mentah): kalau admin
        # memakai provider `custom` dengan base_url kosong, SDK akan jatuh ke
        # api.openai.com dan key OpenRouter ditolak 401.
        "AI_BASE_URL": effective_base_url(cfg) or "",
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
