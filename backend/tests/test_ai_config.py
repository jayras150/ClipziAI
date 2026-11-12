"""Regression test setelan AI: enkripsi key, normalisasi, injeksi env."""
import os

from app.core.config import get_settings
from app.services import ai_config


def test_api_key_dienkripsi_dan_tidak_bisa_dibaca_langsung():
    enc = ai_config.encrypt_api_key("sk-or-secret-1234567890")
    assert enc and "sk-or-secret" not in enc
    assert ai_config.decrypt_api_key(enc) == "sk-or-secret-1234567890"
    assert ai_config.mask_api_key("sk-or-secret-1234567890") == "sk-o...7890"


def test_normalisasi_clamp_dan_provider_invalid():
    cfg = ai_config.normalize_ai(
        {"provider": "ngawur", "temperature": 9, "max_tokens": 5, "timeout_seconds": 9999}
    )
    assert cfg["provider"] == "custom"
    assert cfg["temperature"] == 1.5
    assert cfg["max_tokens"] == 128
    assert cfg["timeout_seconds"] == 300


def test_base_url_wajib_http():
    assert ai_config.normalize_ai({"base_url": "ftp://x"})["base_url"] == ""
    assert ai_config.normalize_ai({"base_url": "https://ai.test/v1"})["base_url"] == "https://ai.test/v1"


def test_public_config_tidak_membocorkan_key():
    cfg = ai_config.normalize_ai(
        {"provider": "openrouter", "api_key_enc": ai_config.encrypt_api_key("sk-or-abcdefgh12345")}
    )
    public = ai_config.public_ai_config(cfg)
    assert "api_key_enc" not in public
    assert public["api_key_set"] is True
    assert public["api_key_masked"] == "sk-o...2345"
    assert public["effective_base_url"] == "https://openrouter.ai/api/v1"


def test_ai_is_configured_butuh_key_atau_ollama():
    tanpa_key = ai_config.normalize_ai({"enabled": True, "provider": "openrouter"})
    assert ai_config.ai_is_configured(tanpa_key) is False
    dengan_key = ai_config.normalize_ai(
        {"enabled": True, "provider": "openrouter", "api_key_enc": ai_config.encrypt_api_key("x1234567890")}
    )
    assert ai_config.ai_is_configured(dengan_key) is True
    ollama = ai_config.normalize_ai({"enabled": True, "provider": "ollama", "base_url": "http://localhost:11434/v1"})
    assert ai_config.ai_is_configured(ollama) is True
    nonaktif = ai_config.normalize_ai(
        {"enabled": False, "provider": "openrouter", "api_key_enc": ai_config.encrypt_api_key("x1234567890")}
    )
    assert ai_config.ai_is_configured(nonaktif) is False


def test_injeksi_env_langsung_berlaku_untuk_seluruh_sistem(monkeypatch):
    cfg = ai_config.normalize_ai(
        {
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("sk-or-live-999999"),
            "model_metadata": "openai/gpt-4o-mini",
            "model_rerank": "openai/gpt-4o",
            "model_regenerate": "openai/gpt-6-luna",
            "temperature": 0.3,
            "max_tokens": 512,
        }
    )
    result = ai_config.apply_ai_config_to_env(cfg)

    assert os.environ["AI_PROVIDER"] == "openrouter"
    assert os.environ["AI_API_KEY"] == "sk-or-live-999999"
    assert os.environ["AI_RERANK_MODEL"] == "openai/gpt-4o"
    settings = get_settings()
    assert settings.AI_PROVIDER == "openrouter"
    assert settings.AI_API_KEY == "sk-or-live-999999"
    assert settings.AI_TEMPERATURE == 0.3
    assert settings.AI_MAX_TOKENS == 512
    assert "AI_PROVIDER" in result["injected"]
    assert result["api_key_set"] is True
