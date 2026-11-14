"""Tes pemasangan workflow downloader ke repo GitHub (tanpa jaringan asli)."""
import asyncio
import base64

import pytest

from app.models.download_runner import DownloadRunner
from app.services import runner_manager as rm


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None):
        self.calls.append(("GET", url, params, None))
        return self.routes["get"](url, params)

    async def put(self, url, headers=None, json=None):
        self.calls.append(("PUT", url, None, json))
        return self.routes["put"](url, json)


class FakeDB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _runner(**overrides):
    data = {
        "name": "test",
        "owner": "octo",
        "repo": "demo",
        "workflow_file": "downloader_video.yml",
        "git_ref": "main",
        "auth_mode": "pat",
        "weight": 100,
        "enabled": True,
    }
    data.update(overrides)
    return DownloadRunner(**data)


def _async(value):
    async def _inner():
        return value

    return _inner()


def _patch_client(monkeypatch, routes):
    holder = {}

    def factory(**kwargs):
        holder["client"] = FakeClient(routes)
        return holder["client"]

    monkeypatch.setattr(rm.httpx, "AsyncClient", factory)
    monkeypatch.setattr(rm, "_github_headers", lambda runner: {"Authorization": "Bearer x"})
    return holder


def test_template_is_bundled():
    template = rm.workflow_template()
    assert "workflow_dispatch" in template
    assert "Downloader Video" in template


def test_workflow_status_up_to_date(monkeypatch):
    template = rm.workflow_template()
    encoded = base64.b64encode(template.encode()).decode()

    def get(url, params):
        if url.endswith("/repos/octo/demo"):
            return FakeResponse(200, {"default_branch": "main", "size": 42, "has_actions": True})
        if "/contents/" in url:
            return FakeResponse(
                200,
                {
                    "sha": "abc",
                    "size": len(template),
                    "content": "\n".join(encoded[i : i + 60] for i in range(0, len(encoded), 60)),
                    "html_url": "https://github.com/octo/demo/blob/main/workflow.yml",
                },
            )
        return FakeResponse(
            200, {"workflows": [{"path": ".github/workflows/downloader_video.yml"}]}
        )

    _patch_client(monkeypatch, {"get": get, "put": lambda url, payload: FakeResponse(500)})
    data = asyncio.run(rm.workflow_status(FakeDB(), _runner()))
    assert data["ok"] is True
    assert data["exists"] is True
    assert data["up_to_date"] is True
    assert data["workflow_registered"] is True
    assert data["repo_empty"] is False


def test_install_creates_first_commit_on_empty_repo(monkeypatch):
    status = {
        "ok": True,
        "error": None,
        "path": ".github/workflows/downloader_video.yml",
        "repo": "octo/demo",
        "default_branch": "main",
        "repo_empty": True,
        "exists": False,
        "up_to_date": False,
        "sha": None,
    }
    monkeypatch.setattr(rm, "workflow_status", lambda db, runner: _async(status))
    holder = _patch_client(
        monkeypatch,
        {
            "get": lambda url, params: FakeResponse(500),
            "put": lambda url, payload: FakeResponse(
                201,
                {
                    "content": {"sha": "newsha"},
                    "commit": {"html_url": "https://github.com/octo/demo/commit/1"},
                },
            ),
        },
    )
    result = asyncio.run(rm.install_workflow(FakeDB(), _runner()))
    assert result["action"] == "created"
    assert result["commit_url"].endswith("/commit/1")
    payload = holder["client"].calls[-1][3]
    assert "branch" not in payload  # repo kosong: tanpa branch
    assert payload["content"]


def test_install_refuses_to_overwrite_without_force(monkeypatch):
    status = {
        "ok": True,
        "error": None,
        "path": ".github/workflows/downloader_video.yml",
        "repo": "octo/demo",
        "default_branch": "main",
        "repo_empty": False,
        "exists": True,
        "up_to_date": False,
        "sha": "old",
    }
    monkeypatch.setattr(rm, "workflow_status", lambda db, runner: _async(status))
    holder = _patch_client(
        monkeypatch,
        {
            "get": lambda url, params: FakeResponse(500),
            "put": lambda url, payload: FakeResponse(500),
        },
    )
    result = asyncio.run(rm.install_workflow(FakeDB(), _runner()))
    assert result["action"] == "conflict"
    assert holder.get("client") is None  # tidak ada request PUT sama sekali


def test_install_force_updates_existing(monkeypatch):
    status = {
        "ok": True,
        "error": None,
        "path": ".github/workflows/downloader_video.yml",
        "repo": "octo/demo",
        "default_branch": "main",
        "repo_empty": False,
        "exists": True,
        "up_to_date": False,
        "sha": "oldsha",
    }
    monkeypatch.setattr(rm, "workflow_status", lambda db, runner: _async(status))
    holder = _patch_client(
        monkeypatch,
        {
            "get": lambda url, params: FakeResponse(500),
            "put": lambda url, payload: FakeResponse(
                200,
                {"content": {"sha": "newsha"}, "commit": {"html_url": "https://github.com/c/2"}},
            ),
        },
    )
    result = asyncio.run(rm.install_workflow(FakeDB(), _runner(), force=True))
    assert result["action"] == "updated"
    payload = holder["client"].calls[-1][3]
    assert payload["sha"] == "oldsha"
    assert payload["branch"] == "main"


def test_install_maps_permission_error(monkeypatch):
    status = {"ok": False, "error": "Pasang workflow gagal: GitHub menolak izin (Forbidden)."}
    monkeypatch.setattr(rm, "workflow_status", lambda db, runner: _async(status))
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(rm.install_workflow(FakeDB(), _runner(), force=True))
    assert "izin" in str(exc.value).lower()
