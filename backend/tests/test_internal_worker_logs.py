"""
Test endpoint webhook log worker (`POST /api/internal/worker/logs`).

Regresi: model `WorkerLogBatch` dulu memakai `List[dict]` di dalam modul yang
memakai `from __future__ import annotations`. Pydantic 2.13 gagal me-resolve
tipe itu sehingga endpoint SELALU membalas 500 dan seluruh log worker (termasuk
log onstart sebelum pipeline) hilang tanpa jejak di dashboard admin.
"""
from __future__ import annotations

import asyncio
import json

from app.api import internal


class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = headers or {}


def test_worker_log_batch_bisa_divalidasi():
    """Model harus bisa diinstansiasi + di-dump (dulu raise PydanticUserError)."""
    batch = internal.WorkerLogBatch(
        task_id=None,
        instance_id=123,
        lines=[{"seq": 1, "level": "INFO", "stage": "boot", "message": "halo"}],
    )
    dumped = [line.model_dump() for line in batch.lines]
    assert dumped == [{"seq": 1, "level": "INFO", "stage": "boot", "message": "halo"}]


def test_worker_log_batch_default_kosong():
    batch = internal.WorkerLogBatch()
    assert batch.lines == []
    assert batch.task_id is None


def test_worker_logs_ingest_menyimpan_baris(monkeypatch):
    """Handler meneruskan baris ke penyimpanan dan membalas ok=True."""
    from app.services import worker_log_lines

    captured: dict = {}

    async def fake_append(db, *, task_id, instance_id, lines):
        captured.update(task_id=task_id, instance_id=instance_id, lines=lines)
        return {"stored": len(lines), "max_seq": max((l["seq"] for l in lines), default=0)}

    monkeypatch.setattr(worker_log_lines, "append_lines", fake_append)
    # Handler mengimpor get_settings di dalam fungsi, jadi patch di modul asalnya.
    from app.core import config as core_config

    monkeypatch.setattr(
        core_config, "get_settings", lambda: type("S", (), {"CLIPZI_WORKER_TOKEN": "tok"})()
    )

    payload = internal.WorkerLogBatch(
        task_id=None,
        instance_id=999,
        lines=[{"seq": 1, "level": "INFO", "stage": "boot", "message": "onstart"}],
    )
    result = asyncio.run(
        internal.worker_logs_ingest(
            payload, _FakeRequest({"x-clipzi-token": "tok"}), db=object()
        )
    )

    assert result["ok"] is True
    assert result["stored"] == 1
    assert captured["instance_id"] == 999
    assert captured["lines"][0]["message"] == "onstart"


def test_worker_logs_ingest_menolak_token_salah(monkeypatch):
    from fastapi import HTTPException

    from app.core import config as core_config

    monkeypatch.setattr(
        core_config, "get_settings", lambda: type("S", (), {"CLIPZI_WORKER_TOKEN": "tok"})()
    )
    payload = internal.WorkerLogBatch(lines=[])

    try:
        asyncio.run(
            internal.worker_logs_ingest(
                payload, _FakeRequest({"x-clipzi-token": "salah"}), db=object()
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 401
    else:  # pragma: no cover
        raise AssertionError("token salah seharusnya ditolak")
