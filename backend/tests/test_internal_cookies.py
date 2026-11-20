"""Test endpoint cookies internal: worker mengambil cookies tanpa lewat env Vast.

Yang dijaga:
  - cookies tetap tersedia untuk worker walau env Vast tidak lagi memuat
    `YTDLP_COOKIES_*` (batas env ±4 KB, dan metadata instance Vast terbaca
    dari dashboard);
  - endpoint TIDAK terbuka tanpa token, dan tidak 500 saat cookies kosong.
"""
from __future__ import annotations

import asyncio

import pytest


class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}


def _settings_with_token(monkeypatch, token: str = "tok"):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "CLIPZI_WORKER_TOKEN", token, raising=False)
    return settings


def test_tanpa_token_config_503(monkeypatch):
    from fastapi import HTTPException

    from app.api import internal

    _settings_with_token(monkeypatch, "")
    with pytest.raises(HTTPException) as exc:
        internal._verify_agent_token(_FakeRequest({"x-clipzi-token": "abc"}))
    assert exc.value.status_code == 503


def test_token_salah_401(monkeypatch):
    from fastapi import HTTPException

    from app.api import internal

    _settings_with_token(monkeypatch, "rahasia")
    with pytest.raises(HTTPException) as exc:
        internal._verify_agent_token(_FakeRequest({"x-clipzi-token": "salah"}))
    assert exc.value.status_code == 401


def test_mengembalikan_cookies_aktif(monkeypatch):
    from app.api import internal
    from app.services import runtime_credentials as rc

    _settings_with_token(monkeypatch, "rahasia")

    async def _fake_text():
        return (
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\tabc\n",
            "platform_settings",
        )

    monkeypatch.setattr(rc, "read_active_cookies_text", _fake_text)

    response = asyncio.run(
        internal.active_cookies(_FakeRequest({"x-clipzi-token": "rahasia"}))
    )

    assert response.status_code == 200
    assert b"SID" in response.body
    assert str(response.media_type).startswith("text/plain")


def test_tanpa_cookies_204(monkeypatch):
    from app.api import internal
    from app.services import runtime_credentials as rc

    _settings_with_token(monkeypatch, "rahasia")

    async def _empty():
        return "", ""

    monkeypatch.setattr(rc, "read_active_cookies_text", _empty)

    response = asyncio.run(
        internal.active_cookies(_FakeRequest({"x-clipzi-token": "rahasia"}))
    )

    assert response.status_code == 204
    assert not response.body
