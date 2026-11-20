"""Regresi: kredensial DB harus muncul di env worker.

Bug yang dijaga:
  - tab admin *Instance -> Environment* menampilkan cookies/HF token "kosong"
    karena `build_worker_env()` hanya membaca env proses;
  - `HF_TOKEN` tidak ada di `Settings` sehingga tidak pernah dikirim ke worker.
"""
import asyncio

from app.core.config import get_settings
from app.services import runtime_credentials as rc
from app.services.vast_worker import build_worker_env

COOKIES_B64 = "Y29va2llcw=="


async def _fake_cookies():
    return (COOKIES_B64, "platform_settings")


async def _fake_token():
    return "hf_test_token"


def _hydrate(monkeypatch):
    settings = get_settings()
    settings.YTDLP_COOKIES_BASE64 = None
    settings.HF_TOKEN = None
    # Default produksi: cookies TIDAK dikirim lewat env (lihat CLIPZI_COOKIES_VIA_ENV).
    settings.CLIPZI_COOKIES_VIA_ENV = False
    monkeypatch.setattr(rc, "_read_youtube_base64", _fake_cookies)
    monkeypatch.setattr(rc, "_read_hf_token", _fake_token)
    monkeypatch.setattr(rc, "_apply_storage", lambda config: {"storage_set": False})
    return asyncio.run(rc.hydrate_runtime_credentials())


def test_hydrate_mengisi_settings_dan_env_worker(monkeypatch):
    summary = _hydrate(monkeypatch)

    assert summary["youtube"]["cookies_set"] is True
    assert summary["youtube"]["cookies_source"] == "platform_settings"
    assert summary["huggingface"]["hf_token_set"] is True

    settings = get_settings()
    assert settings.YTDLP_COOKIES_BASE64 == COOKIES_B64
    assert settings.HF_TOKEN == "hf_test_token"

    env = build_worker_env()
    assert env["HF_TOKEN"] == "hf_test_token"
    # Cookies diambil worker dari /api/internal/cookies/active.txt atau pool
    # tabel ytdlp_cookies, bukan dari env (hemat ~2 KB anggaran env Vast).
    assert "YTDLP_COOKIES_BASE64" not in env
    assert "YTDLP_COOKIES_GZIP_B64" not in env


def test_cookies_via_env_flag_mengembalikan_perilaku_lama(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "CLIPZI_COOKIES_VIA_ENV", True, raising=False)
    monkeypatch.setattr(
        settings, "YTDLP_COOKIES_BASE64", COOKIES_B64, raising=False
    )

    env = build_worker_env()

    # Payload kecil -> tidak dipadatkan, cookies tetap dikirim seperti dulu.
    assert env.get("YTDLP_COOKIES_BASE64") == COOKIES_B64


def test_settings_punya_field_hf_token():
    assert "HF_TOKEN" in get_settings().__class__.model_fields


def test_encode_cookies_base64():
    assert rc.encode_cookies_base64("abc") == "YWJj"
    assert rc.encode_cookies_base64("") == ""


def test_hydrate_tanpa_data_tidak_menimpa(monkeypatch):
    settings = get_settings()
    settings.YTDLP_COOKIES_BASE64 = "existing"
    settings.HF_TOKEN = "existing-token"

    async def _empty_cookies():
        return ("", "")

    async def _empty_token():
        return ""

    monkeypatch.setattr(rc, "_read_youtube_base64", _empty_cookies)
    monkeypatch.setattr(rc, "_read_hf_token", _empty_token)
    monkeypatch.setattr(rc, "_apply_storage", lambda config: {"storage_set": False})

    summary = asyncio.run(rc.hydrate_runtime_credentials())

    assert summary["youtube"]["cookies_set"] is False
    assert summary["huggingface"]["hf_token_set"] is False
    assert settings.YTDLP_COOKIES_BASE64 == "existing"
    assert settings.HF_TOKEN == "existing-token"
