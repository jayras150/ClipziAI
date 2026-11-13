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
        {
            "enabled": True,
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("sk-or-v1-0123456789abcdef"),
        }
    )
    assert ai_config.ai_is_configured(dengan_key) is True
    ollama = ai_config.normalize_ai({"enabled": True, "provider": "ollama", "base_url": "http://localhost:11434/v1"})
    assert ai_config.ai_is_configured(ollama) is True
    nonaktif = ai_config.normalize_ai(
        {
            "enabled": False,
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("sk-or-v1-0123456789abcdef"),
        }
    )
    assert ai_config.ai_is_configured(nonaktif) is False
    # key berisi Base URL tidak boleh dianggap siap (penyebab 401 OpenRouter)
    url_key = ai_config.normalize_ai(
        {
            "enabled": True,
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("https://openrouter.ai/api/v1"),
        }
    )
    assert ai_config.ai_is_configured(url_key) is False


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



class _FakeRow:
    def __init__(self, value):
        self.value = value


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    """DB minimum untuk `set_ai_config` (tanpa Postgres)."""

    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.commits = 0

    async def execute(self, *_a, **_k):
        return _FakeResult(self.row)

    def add(self, obj):
        self.added.append(obj)
        self.row = _FakeRow(getattr(obj, "value", None))

    async def commit(self):
        self.commits += 1


def _run_set(payload, current=None):
    import asyncio

    from app.models.platform_setting import PlatformSetting

    cfg = ai_config.normalize_ai(current) if current else None
    row = _FakeRow(cfg) if cfg else None
    db = _FakeDB(row)
    ai_config.clear_cache()
    try:
        result = asyncio.run(ai_config.set_ai_config(db, payload))
    finally:
        ai_config.clear_cache()
    assert db.commits >= 1
    # Pastikan nilai yang disimpan memang konfigurasi baru.
    if db.row is not None:
        saved = db.row.value if isinstance(db.row.value, dict) else None
    else:
        saved = None
    return result, saved


def test_validate_api_key_menolak_base_url():
    import pytest

    with pytest.raises(ValueError) as exc:
        ai_config.validate_api_key("https://openrouter.ai/api/v1", "openrouter")
    assert "Base URL" in str(exc.value)

    with pytest.raises(ValueError):
        ai_config.validate_api_key("short", "openrouter")

    with pytest.raises(ValueError):
        ai_config.validate_api_key("sk-or-v1 punya spasi di tengah", "openrouter")

    # key wajar tidak melempar
    ai_config.validate_api_key("sk-or-v1-0123456789abcdef0123456789abcdef", "openrouter")


def test_hint_menandai_key_berisi_base_url():
    cfg = ai_config.normalize_ai(
        {
            "enabled": True,
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("https://openrouter.ai/api/v1"),
        }
    )
    hint = ai_config.ai_status_hint(cfg)
    assert hint and "base url" in hint.lower()


def test_simpan_key_base_url_ditolak():
    import pytest

    with pytest.raises(ValueError):
        _run_set({"api_key": "https://openrouter.ai/api/v1"}, current={"provider": "openrouter"})

def test_simpan_api_key_baru_otomatis_mengaktifkan_ai():
    """Bug: toggle 'AI aktif' pernah dimatikan -> key benar tapi AI tetap mati."""
    result, _saved = _run_set(
        {"api_key": "sk-or-baru-1234567890"},
        current={"enabled": False, "provider": "openrouter"},
    )
    assert result["enabled"] is True
    assert ai_config.ai_is_configured(result) is True


def test_enabled_none_tidak_menimpa_status_lama():
    result, _saved = _run_set(
        {"enabled": None, "model_metadata": "openai/gpt-4o-mini"},
        current={"enabled": False, "provider": "openrouter"},
    )
    assert result["enabled"] is False


def test_hint_menjelaskan_ai_dinonaktifkan():
    cfg = ai_config.normalize_ai(
        {"enabled": False, "provider": "openrouter", "api_key_enc": ai_config.encrypt_api_key("sk-x-1234567890")}
    )
    hint = ai_config.ai_status_hint(cfg)
    assert hint and "dinonaktifkan" in hint.lower()


def test_hint_menjelaskan_api_key_kosong():
    cfg = ai_config.normalize_ai({"enabled": True, "provider": "openrouter"})
    hint = ai_config.ai_status_hint(cfg)
    assert hint and "api key kosong" in hint.lower()


def test_public_config_menyertakan_status_siap():
    cfg = ai_config.normalize_ai(
        {
            "enabled": True,
            "provider": "openrouter",
            "api_key_enc": ai_config.encrypt_api_key("sk-or-v1-0123456789abcdef"),
        }
    )
    public = ai_config.public_ai_config(cfg)
    assert public["ready"] is True
    assert public["status_hint"] is None

