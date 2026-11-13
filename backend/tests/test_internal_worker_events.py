"""
Test endpoint internal worker: model `WorkerEvent` harus ada dan handler
menerima event yang sah (dulu class-nya hilang sehingga semua callback
dibalas 400 dan status boot worker tidak pernah tercatat).
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace


class _FakeResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(None)

    async def commit(self):
        self.commits += 1


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    async def body(self) -> bytes:
        return self._body


def test_worker_event_model_tersedia():
    from app.api import internal

    event = internal.WorkerEvent(task_id="abc", event="boot")
    assert event.progress is None
    assert event.instance_id is None


def test_worker_event_diterima(monkeypatch):
    from app.api import internal

    monkeypatch.setattr(internal, "_verify_signature", lambda body, sig: None)

    body = json.dumps(
        {"task_id": "7b1c1c1e-0000-0000-0000-000000000000", "event": "boot"}
    ).encode()
    db = _FakeDB()

    result = asyncio.run(internal.worker_events(_FakeRequest(body), db))

    assert result == {"ok": True}


def test_worker_event_payload_tidak_valid_400(monkeypatch):
    from fastapi import HTTPException

    from app.api import internal

    monkeypatch.setattr(internal, "_verify_signature", lambda body, sig: None)

    try:
        asyncio.run(internal.worker_events(_FakeRequest(b"{}"), _FakeDB()))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Invalid payload" in str(exc.detail)
    else:  # pragma: no cover - seharusnya selalu raise
        raise AssertionError("payload kosong seharusnya ditolak")
