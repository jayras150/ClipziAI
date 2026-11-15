"""Tes template worker Vast.ai otomatis (env pipeline, hash, aktivasi dispatch)."""
import asyncio
from typing import Any, cast

import pytest

from app.core.config import get_settings
from app.services import vast_admin


def test_template_env_string_skips_task_id_and_quotes():
    text = vast_admin.template_env_string(
        {
            "CLIPZI_ROLE": "worker",
            "CLIPZI_TASK_ID": "task-123",
            "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/db",
            "SECRET_KEY": "a b$c",
        }
    )
    assert text.startswith("-p 8000:8000")
    assert "-e CLIPZI_ROLE=worker" in text
    assert "CLIPZI_TASK_ID" not in text
    assert "-e DATABASE_URL=postgresql+asyncpg://u:p@h:5432/db" in text
    assert "-e SECRET_KEY='a b$c'" in text


def test_template_hash_extraction_handles_shapes():
    assert (
        vast_admin._template_hash_from(
            {"success": True, "template": {"id": 3, "hash_id": "h1"}}
        )
        == "h1"
    )
    assert vast_admin._template_hash_from({"hash_id": "h2"}) == "h2"
    assert vast_admin._template_hash_from({"template": "h3"}) == "h3"
    assert vast_admin._template_hash_from({"success": False}) == ""
    assert vast_admin._template_hash_from("a" * 32) == "a" * 32


def test_worker_template_spec_reports_missing_required(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        vast_admin,
        "build_worker_env",
        lambda task_id=None: {"CLIPZI_ROLE": "worker", "DATABASE_URL": "koneksi"},
    )
    monkeypatch.setattr(settings, "VAST_TEMPLATE_HASH", "abc123", raising=False)
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "img:worker", raising=False)
    monkeypatch.setattr(settings, "VAST_API_KEY", "api-key", raising=False)

    spec = vast_admin.worker_template_spec()

    assert spec["template_hash"] == "abc123"
    assert spec["onstart"] == "/app/deployments/pipeline_onstart.sh"
    assert spec["env_count"] == 2
    assert "DATABASE_URL" not in spec["missing_required"]
    assert "CLIPZI_WORKER_TOKEN" in spec["missing_required"]
    assert spec["ready"] is True


def test_create_worker_template_calls_sdk_and_syncs_env(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(settings, "VAST_TEMPLATE_NAME", "clipzi-worker", raising=False)
    monkeypatch.setattr(settings, "VAST_WORKER_DISK", 40, raising=False)
    monkeypatch.setattr(
        vast_admin,
        "build_worker_env",
        lambda task_id=None: {
            "CLIPZI_ROLE": "worker",
            "CLIPZI_TASK_ID": "task-1",
            "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
            "CLIPZI_WORKER_TOKEN": "tok",
            "CLIPZI_CALLBACK_URL": "https://x/api/internal/worker/events",
            "SECRET_KEY": "s3cr3t",
            "ENCRYPTION_KEY": "enc-key",
        },
    )

    class FakeClient:
        def __init__(self):
            self.created: dict[str, Any] | None = None

        def create_template(self, **kwargs):
            self.created = kwargs
            return {"success": True, "template": {"id": 11, "hash_id": "hash-abc"}}

        def search_templates(self, query=None):
            return []

    client = FakeClient()
    synced = {}

    async def fake_sync(keys=None, dry_run=False):
        synced["keys"] = keys
        synced["dry_run"] = dry_run
        return {"dry_run": dry_run, "results": [], "summary": {"same": 4}}

    monkeypatch.setattr(vast_admin, "_client", lambda: client)
    monkeypatch.setattr(vast_admin, "sync_env_to_vast", fake_sync)

    result = asyncio.run(vast_admin.create_worker_template(include_env=True))

    assert result["ok"] is True
    assert result["template_hash"] == "hash-abc"
    assert result["template_id"] == 11
    assert result["env_count"] == 6
    assert result["warnings"] == []
    sent = client.created or {}
    assert sent["name"] == "clipzi-worker"
    assert sent["image"] == "user/clipzi:worker"
    assert sent["onstart_cmd"] == "/app/deployments/pipeline_onstart.sh"
    assert sent["disk_space"] == 40.0
    assert "-e DATABASE_URL=" in sent["env"]
    assert "CLIPZI_TASK_ID" not in sent["env"]
    assert synced == {"keys": None, "dry_run": False}


def test_create_worker_template_without_env_only_docker_options(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(
        vast_admin, "build_worker_env", lambda task_id=None: {"CLIPZI_ROLE": "worker"}
    )

    class FakeClient:
        def create_template(self, **kwargs):
            self.created = kwargs
            return {"success": True, "template": {"hash_id": "hash-noenv"}}

    client = FakeClient()
    monkeypatch.setattr(vast_admin, "_client", lambda: client)

    result = asyncio.run(
        vast_admin.create_worker_template(include_env=False, sync_env_vars=False)
    )

    assert result["env_included"] is False
    assert result["env_sync"]["skipped"] is True
    assert client.created["env"] == "-p 8000:8000"


def test_create_worker_template_default_membekukan_env(monkeypatch):
    """Default: env pipeline ikut dibekukan di template (muncul di web Vast)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(
        vast_admin,
        "build_worker_env",
        lambda task_id=None: {
            "CLIPZI_ROLE": "worker",
            "CLIPZI_TASK_ID": "task-harus-dibuang",
            "DATABASE_URL": "koneksi",
        },
    )

    class FakeClient:
        def create_template(self, **kwargs):
            self.created = kwargs
            return {"success": True, "template": {"hash_id": "hash-default"}}

    client = FakeClient()
    monkeypatch.setattr(vast_admin, "_client", lambda: client)

    result = asyncio.run(vast_admin.create_worker_template(sync_env_vars=False))

    assert result["env_included"] is True
    env = client.created["env"]
    assert "-e CLIPZI_ROLE=worker" in env
    assert "-e DATABASE_URL=koneksi" in env
    assert "CLIPZI_TASK_ID" not in env  # selalu per task
    assert client.created["onstart_cmd"] == "/app/deployments/pipeline_onstart.sh"


def test_create_worker_template_include_env_false(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(
        vast_admin, "build_worker_env", lambda task_id=None: {"CLIPZI_ROLE": "worker"}
    )

    class FakeClient:
        def create_template(self, **kwargs):
            self.created = kwargs
            return {"success": True, "template": {"hash_id": "hash-noenv"}}

    client = FakeClient()
    monkeypatch.setattr(vast_admin, "_client", lambda: client)

    result = asyncio.run(
        vast_admin.create_worker_template(include_env=False, sync_env_vars=False)
    )

    assert result["env_included"] is False
    assert result["env_count"] == 0
    assert client.created["env"] == "-p 8000:8000"


def test_create_worker_template_falls_back_to_search(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(settings, "VAST_TEMPLATE_NAME", "clipzi-worker", raising=False)
    monkeypatch.setattr(
        vast_admin, "build_worker_env", lambda task_id=None: {"CLIPZI_ROLE": "worker"}
    )

    class FakeClient:
        def create_template(self, **kwargs):
            return {"success": True, "template": {"id": 5}}

        def search_templates(self, query=None):
            return [
                {"name": "clipzi-worker", "hash_id": "older", "created_at": 10},
                {"name": "clipzi-worker", "hash_id": "newer", "created_at": 20},
                {"name": "template-lain", "hash_id": "other", "created_at": 99},
            ]

    monkeypatch.setattr(vast_admin, "_client", lambda: FakeClient())

    result = asyncio.run(vast_admin.create_worker_template(sync_env_vars=False))

    assert result["template_hash"] == "newer"
    assert result["ok"] is True


def test_create_worker_template_requires_image(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "", raising=False)
    monkeypatch.setattr(vast_admin, "_client", lambda: object())

    with pytest.raises(RuntimeError):
        asyncio.run(vast_admin.create_worker_template(sync_env_vars=False))


def test_build_template_env_respects_vast_4096_limit():
    """Vast: 'Param env greater than max length 4096 chars'."""
    env = {
        "CLIPZI_ROLE": "worker",
        "DATABASE_URL": "postgresql+asyncpg://u:p@h:5432/db",
        "CLIPZI_WORKER_TOKEN": "tok",
        "YTDLP_COOKIES_BASE64": "x" * 6000,
    }
    text, included, skipped = vast_admin.build_template_env(env)

    assert len(text) <= vast_admin.TEMPLATE_ENV_MAX_LEN
    assert "DATABASE_URL" in included
    assert "CLIPZI_WORKER_TOKEN" in included
    assert "YTDLP_COOKIES_BASE64" in skipped
    assert "YTDLP_COOKIES_BASE64" not in text


def test_create_worker_template_wraps_vast_http_error(monkeypatch):
    """HTTP 400 dari Vast tidak boleh jadi 500; pesannya harus terbaca."""
    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "user/clipzi:worker", raising=False)
    monkeypatch.setattr(
        vast_admin, "build_worker_env", lambda task_id=None: {"CLIPZI_ROLE": "worker"}
    )

    class FakeResponse:
        status_code = 400
        text = '{"error":"invalid_params","msg":"Param env greater than max length 4096 chars"}'

    class FakeHTTPError(Exception):
        response = FakeResponse()

    class FakeClient:
        def create_template(self, **kwargs):
            raise FakeHTTPError("400 Client Error: Bad Request")

    monkeypatch.setattr(vast_admin, "_client", lambda: FakeClient())

    with pytest.raises(RuntimeError) as excinfo:
        asyncio.run(vast_admin.create_worker_template(sync_env_vars=False))

    message = str(excinfo.value)
    assert "HTTP 400" in message
    assert "max length 4096" in message


def test_admin_endpoint_activates_template(monkeypatch):
    from app.api.admin import vast as vast_api

    saved = {}

    async def fake_create(**kwargs):
        return {
            "ok": True,
            "template_hash": "hash-endpoint",
            "image": "user/clipzi:worker",
            "disk_space": 40,
            "name": "clipzi-worker",
            "env_count": 3,
        }

    async def fake_save(db, payload):
        saved.update(payload)
        return {}

    class FakeDB:
        def add(self, _row):
            return None

        async def commit(self):
            return None

    class FakeAdmin:
        id = 1
        email = "admin@clipzi.test"

    class FakeRequest:
        client = None
        headers = {}

    monkeypatch.setattr(vast_api.vast_admin, "create_worker_template", fake_create)
    monkeypatch.setattr(vast_api.vast_config, "save_vast_config", fake_save)

    result = asyncio.run(
        vast_api.create_worker_template(
            vast_api.TemplateCreateIn(),
            cast(Any, FakeRequest()),
            cast(Any, FakeAdmin()),
            cast(Any, FakeDB()),
        )
    )

    assert result["activated"] is True
    assert saved == {
        "template_hash": "hash-endpoint",
        "worker_image": "user/clipzi:worker",
        "worker_disk": 40,
    }
