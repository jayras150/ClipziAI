"""Regresi: base URL AI harus konsisten dengan API key yang dipakai.

Bug asli: admin mengisi provider `custom`, `base_url` kosong, tetapi
`endpoint_chat=https://openrouter.ai/api/v1/`. SDK OpenAI-compatible jatuh ke
default api.openai.com -> key OpenRouter (`sk-or-v1…`) ditolak 401, request
regenerate metadata menggantung lalu Cloudflare menampilkan 520.
"""
from app.services.ai_config import (
    _strip_endpoint_path,
    effective_base_url,
    encrypt_api_key,
)
from app.services.metadata_generator import _is_auth_error

OR_KEY = "sk-or-v1-0123456789abcdef"


def test_base_url_diturunkan_dari_endpoint_chat():
    cfg = {
        "provider": "custom",
        "base_url": "",
        "endpoint_chat": "https://openrouter.ai/api/v1/",
        "api_key_enc": encrypt_api_key(OR_KEY),
    }

    assert effective_base_url(cfg) == "https://openrouter.ai/api/v1"


def test_base_url_diturunkan_dari_endpoint_penuh():
    cfg = {
        "provider": "custom",
        "base_url": "",
        "endpoint_chat": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_enc": encrypt_api_key(OR_KEY),
    }

    assert effective_base_url(cfg) == "https://openrouter.ai/api/v1"


def test_key_openrouter_tidak_dikirim_ke_openai():
    cfg = {
        "provider": "openai",
        "base_url": "",
        "api_key_enc": encrypt_api_key(OR_KEY),
    }

    assert effective_base_url(cfg) == "https://openrouter.ai/api/v1"


def test_base_url_eksplisit_selalu_menang():
    cfg = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_enc": encrypt_api_key("sk-proj-real-openai-key"),
    }

    assert effective_base_url(cfg) == "https://api.openai.com/v1"


def test_strip_path_endpoint():
    assert (
        _strip_endpoint_path("https://x.dev/v1/chat/completions") == "https://x.dev/v1"
    )
    assert (
        _strip_endpoint_path("https://x.dev/v1/audio/transcriptions") == "https://x.dev/v1"
    )
    assert _strip_endpoint_path("https://x.dev/v1/") == "https://x.dev/v1"


def test_deteksi_error_auth_provider():
    assert _is_auth_error("Error code: 401 - Incorrect API key provided: sk-or-v1…")
    assert _is_auth_error("Error code: 403 - Forbidden")
    assert not _is_auth_error("Error code: 429 - rate limited")
    assert not _is_auth_error("empty response from model")
