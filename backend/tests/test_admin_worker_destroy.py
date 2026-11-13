"""
Test admin destroy instance: 404 dari Vast harus dianggap sukses.

Regresi: instance yang sudah tidak ada di Vast tetap ditolak 502 dan barisnya
tidak pernah ditandai `destroyed`, sehingga baris "ghost" menumpuk dan
supervisor terus menganggapnya hidup.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _Row:
    def __init__(self):
        self.state = "running"
        self.destroy_reason = None


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, row):
        self.row = row
        self.commits = 0

    async def execute(self, *_a, **_k):
        return _FakeResult(self.row)

    async def commit(self):
        self.commits += 1


def _admin():
    return SimpleNamespace(id="00000000-0000-0000-0000-000000000001", email="admin@clipzi.test")


def _run(monkeypatch, exc):
    from app.api.admin import workers as mod

    class _Client:
        def destroy_instance(self, instance_id):  # noqa: ANN001
            if exc is not None:
                raise exc
            return {"success": True}

    monkeypatch.setattr("app.services.vast_worker._get_vast_client", lambda: _Client())
    monkeypatch.setattr(
        mod, "get_settings", lambda: SimpleNamespace(VAST_API_KEY="dummy")
    )

    row = _Row()
    db = _FakeDB(row)
    result = asyncio.run(mod.destroy_worker_instance(123, _admin(), db))
    return result, row


def test_destroy_404_dianggap_sukses(monkeypatch):
    result, row = _run(monkeypatch, Exception("404 Client Error: Not Found for url: ..."))
    assert result["ok"] is True
    assert result["already_gone"] is True
    assert row.state == "destroyed"
    assert "sudah tidak ada" in row.destroy_reason


def test_destroy_galat_lain_tetap_502(monkeypatch):
    with pytest.raises(HTTPException) as excinfo:
        _run(monkeypatch, Exception("500 Server Error: internal"))
    assert excinfo.value.status_code == 502
