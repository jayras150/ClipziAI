"""Regresi: kredensial AI per fitur (Base URL + API key sendiri).

Setiap fitur (metadata, rerank, regenerate, transkripsi, viral) boleh punya
Base URL dan API key sendiri. Bila kosong, otomatis memakai kredensial utama
sehingga konfigurasi lama tetap berjalan.
"""
from __future__ import annotations

from app.services.ai_config import (
    ROLES,
    encrypt_api_key,
    normalize_ai,
    public_ai_config,
    resolve_role,
    role_status,
)


def test_semua_fitur_punya_status():
    cfg = normalize_ai({})
    status = {item["role"]: item for item in role_status(cfg)}

    assert set(status) == set(ROLES)
    for role in ROLES:
        assert status[role]["label"]
        assert "uses_role_key" in status[role]


def test_tanpa_role_memakai_kredensial_utama():
    cfg = normalize_ai(
        {
            "base_url": "https://global.example/v1",
            "api_key_enc": encrypt_api_key("global-key"),
        }
    )

    info = resolve_role(cfg, "rerank")

    assert info["base_url"] == "https://global.example/v1"
    assert info["api_key"] == "global-key"
    assert info["uses_role_key"] is False
    assert info["uses_role_base_url"] is False
    assert info["url"].endswith("/rerank")


def test_role_punya_base_url_dan_key_sendiri():
    cfg = normalize_ai(
        {
            "base_url": "https://global.example/v1",
            "api_key_enc": encrypt_api_key("global-key"),
            "role_base_urls": {"metadata": "https://meta.example/v1"},
            "role_api_key_enc": {"metadata": encrypt_api_key("meta-key")},
            "model_metadata": "meta-model",
        }
    )

    info = resolve_role(cfg, "metadata")

    assert info["base_url"] == "https://meta.example/v1"
    assert info["api_key"] == "meta-key"
    assert info["model"] == "meta-model"
    assert info["uses_role_base_url"] is True
    assert info["uses_role_key"] is True
    assert info["url"] == "https://meta.example/v1/chat/completions"


def test_base_url_role_tidak_valid_diabaikan():
    cfg = normalize_ai({"role_base_urls": {"rerank": "ftp://bukan-http"}})

    assert cfg["role_base_urls"]["rerank"] == ""


def test_public_config_tidak_membocorkan_key():
    cfg = normalize_ai({"role_api_key_enc": {"viral": encrypt_api_key("viral-key")}})

    payload = public_ai_config(cfg)

    assert "api_key_enc" not in payload
    assert "role_api_key_enc" not in payload
    roles = {item["role"]: item for item in payload["roles"]}
    assert roles["viral"]["has_key"] is True
    assert roles["viral"]["uses_role_key"] is True


def test_viral_punya_model_sendiri():
    cfg = normalize_ai({"model_viral": "viral-model"})

    assert resolve_role(cfg, "viral")["model"] == "viral-model"


class _FakeResult:
    def scalar_one_or_none(self):
        return None


class _FakeDB:
    """Session minimal untuk menguji jalur simpan tanpa database nyata."""

    def __init__(self) -> None:
        self.added: list = []
        self.committed = False

    async def execute(self, _stmt):
        return _FakeResult()

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


def test_set_ai_config_menyimpan_kredensial_per_fitur(monkeypatch):
    import asyncio

    import app.services.ai_config as mod

    async def _current(_db):
        return mod.normalize_ai({})

    monkeypatch.setattr(mod, "get_ai_config", _current)
    monkeypatch.setattr(mod, "apply_ai_config_to_env", lambda _cfg: {"injected": []})

    db = _FakeDB()
    cfg = asyncio.run(
        mod.set_ai_config(
            db,
            {
                "role_base_urls": {"rerank": "https://rerank.example/v1"},
                "role_api_keys": {"rerank": "rerank-key"},
            },
        )
    )

    info = mod.resolve_role(cfg, "rerank")
    assert info["base_url"] == "https://rerank.example/v1"
    assert info["api_key"] == "rerank-key"
    assert info["uses_role_key"] is True
    assert db.committed is True


def test_clear_role_keys_menghapus_key_fitur(monkeypatch):
    import asyncio

    import app.services.ai_config as mod

    async def _current(_db):
        return mod.normalize_ai(
            {"role_api_key_enc": {"viral": mod.encrypt_api_key("viral-key")}}
        )

    monkeypatch.setattr(mod, "get_ai_config", _current)
    monkeypatch.setattr(mod, "apply_ai_config_to_env", lambda _cfg: {"injected": []})

    cfg = asyncio.run(mod.set_ai_config(_FakeDB(), {"clear_role_keys": ["viral"]}))

    info = mod.resolve_role(cfg, "viral")
    assert info["uses_role_key"] is False
