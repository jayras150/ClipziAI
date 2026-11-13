"""
Test admin Retry task: status harus kembali ke `queued` **dan** di-dispatch.

Regresi: dulu `POST /api/admin/tasks/{id}/retry` hanya menulis
`status=queued` tanpa memanggil `submit_task`, sehingga task menggantung
selamanya karena tidak ada scheduler yang menarik antrean.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Cukup untuk `retry_task`: execute/commit/add."""

    def __init__(self, task):
        self._task = task
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._task)

    async def commit(self):
        self.commits += 1

    def add(self, _obj):
        return None


def _request():
    return SimpleNamespace(client=None, headers={}, method="POST", url="/x")


def _admin():
    return SimpleNamespace(id=uuid4(), email="admin@clipzi.test")


def _task():
    from app.models.task import Task, TaskStatus

    task = Task()
    task.id = uuid4()
    task.status = TaskStatus.ERROR
    task.progress = 42
    task.error_message = "storage belum dikonfigurasi"
    return task


def _run(monkeypatch, dispatch):
    from app.api.admin import tasks as admin_tasks

    task = _task()
    db = _FakeDB(task)
    fake_submit = AsyncMock(return_value=dispatch)
    monkeypatch.setattr(admin_tasks, "submit_task", fake_submit)
    monkeypatch.setattr(admin_tasks, "dispatch_mode", lambda: "oneshot")

    result = asyncio.run(admin_tasks.retry_task(task.id, _request(), _admin(), db))
    return task, result, fake_submit


def test_retry_mengirim_task_ke_worker(monkeypatch):
    task, result, fake_submit = _run(monkeypatch, {"queued": True})

    fake_submit.assert_awaited_once_with(task.id)
    assert result["status"] == "queued"
    assert result["dispatch_mode"] == "oneshot"
    assert task.error_message is None
    assert task.progress == 0


def test_retry_gagal_dispatch_menandai_error(monkeypatch):
    task, result, fake_submit = _run(
        monkeypatch, {"queued": False, "error": "Vast menolak (no offers)"}
    )

    fake_submit.assert_awaited_once_with(task.id)
    assert result["status"] == "error"
    assert task.status.value == "error"
    assert "no offers" in (task.error_message or "")
    assert "oneshot" in (task.error_message or "")
