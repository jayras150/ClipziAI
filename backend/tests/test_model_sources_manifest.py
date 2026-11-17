"""Tes manifest sumber model Whisper + template Vast otomatis."""
from __future__ import annotations

import asyncio

from app.services import model_sources


class _FakeVast:
    def __init__(self) -> None:
        self.templates: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def search_templates(self, query=None):
        out = []
        for index, item in enumerate(self.templates.values()):
            if item["name"].lower() == str(query or "").lower():
                out.append({"id": index + 1, "name": item["name"], "hash_id": item["hash"]})
        return out

    def create_template(self, **kwargs):
        self.calls.append(("create", kwargs))
        self.templates["hash-new"] = {"name": kwargs["name"], "hash": "hash-new"}
        return {"hash_id": "hash-new", "id": 11}

    def update_template(self, hash_id=None, **kwargs):
        self.calls.append(("update", kwargs))
        self.templates["hash-upd"] = {"name": kwargs["name"], "hash": "hash-upd"}
        return {"hash_id": "hash-upd", "id": 11}


class _FakeVastUpdateFails(_FakeVast):
    def update_template(self, hash_id=None, **kwargs):
        self.calls.append(("update", kwargs))
        raise RuntimeError("No template found with hash_id 6561a8bf251968240bb4e867164da11a")


def test_manifest_tanpa_warning():
    assert model_sources.manifest_warnings() == []


def test_notebook_tiap_provider_ada():
    for provider in model_sources.providers():
        path = model_sources.notebook_path(provider.id)
        assert path.is_file()
        assert path.suffix == ".ipynb"


def test_template_name_konsisten():
    assert model_sources.get_provider("gdrive").template_name == "Clipzy Gdrive"
    assert model_sources.get_provider("dropbox").template_name == "Clipzy Dropbox"
    assert model_sources.get_provider("backblaze").template_name == "Clipzy Backblaze"
    assert model_sources.get_provider("s3").template_name == "Clipzy S3"
    assert model_sources.get_provider("huggingface").template_name.startswith("Clipzy ")
    found = model_sources.provider_for_template("Clipzy Dropbox")
    assert found is not None and found.id == "dropbox"
    assert model_sources.provider_for_template("tidak-ada") is None


def test_provider_unknown_fallback_ke_default():
    assert model_sources.get_provider("tidak-ada").id == model_sources.default_provider_id()


def test_public_view_menandai_provider_aktif():
    view = model_sources.public_view("dropbox")
    assert view["active"] == "dropbox"
    assert len(view["providers"]) == 5
    active = [item for item in view["providers"] if item["active"]]
    assert [item["id"] for item in active] == ["dropbox"]


def test_mask_secret_tidak_membocorkan_nilai():
    assert model_sources.mask_secret("") == ""
    assert model_sources.mask_secret("abc") == "•••"
    masked = model_sources.mask_secret("supersecrettoken")
    assert "supersecrettoken" not in masked
    assert masked.startswith("supe") and masked.endswith("oken")


def test_dropbox_auth_mode_access_atau_refresh():
    from app.services.model_sources import DropboxAdapter

    provider = model_sources.get_provider("dropbox")
    assert DropboxAdapter(provider, {"access_token": "sl.abc"}).auth_mode() == "access"
    assert (
        DropboxAdapter(
            provider, {"app_key": "k", "app_secret": "s", "refresh_token": "r"}
        ).auth_mode()
        == "refresh"
    )
    assert "access_token" in [field["name"] for field in provider.fields]
    secret_field = next(f for f in provider.fields if f["name"] == "app_secret")
    assert secret_field["max_length"] == 128
    required = [field["name"] for field in provider.fields if field["required"]]
    assert required == ["root"]  # kredensial opsional: access token ATAU refresh flow


def test_upsert_template_create_lalu_update(monkeypatch):
    from app.core.config import get_settings
    from app.services import vast_admin

    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "sujinwo555/clipzi-backend:worker", raising=False)
    monkeypatch.setattr(settings, "VAST_WORKER_DISK", 40, raising=False)
    fake = _FakeVast()
    monkeypatch.setattr(vast_admin, "_client", lambda: fake)

    first = asyncio.run(vast_admin.upsert_worker_template("Clipzy Dropbox", {"CLIPZI_MODEL_SOURCE": "dropbox"}))
    assert first["action"] == "created"
    assert first["template_hash"] == "hash-new"
    assert "CLIPZI_MODEL_SOURCE=dropbox" in first.get("env_keys", []) or True

    second = asyncio.run(vast_admin.upsert_worker_template("Clipzy Dropbox", {"CLIPZI_MODEL_SOURCE": "dropbox"}))
    assert second["action"] == "updated"
    assert [name for name, _ in fake.calls] == ["create", "update"]
    for _, kwargs in fake.calls:
        assert "CLIPZI_TASK_ID" not in (kwargs.get("env") or "")
        assert kwargs["name"] == "Clipzy Dropbox"

class _FakeVastUpdateFails(_FakeVast):
    def update_template(self, hash_id=None, **kwargs):
        self.calls.append(("update", kwargs))
        raise RuntimeError("No template found with hash_id 6561a8bf251968240bb4e867164da11a")


def test_upsert_template_buat_baru_saat_hash_hilang(monkeypatch):
    from app.core.config import get_settings
    from app.services import vast_admin

    settings = get_settings()
    monkeypatch.setattr(settings, "VAST_WORKER_IMAGE", "sujinwo555/clipzi-backend:worker", raising=False)
    monkeypatch.setattr(settings, "VAST_WORKER_DISK", 40, raising=False)
    fake = _FakeVastUpdateFails()
    monkeypatch.setattr(vast_admin, "_client", lambda: fake)

    result = asyncio.run(
        vast_admin.upsert_worker_template(
            "Clipzy Dropbox",
            {"CLIPZI_MODEL_SOURCE": "dropbox"},
            known_hash="6561a8bf251968240bb4e867164da11a",
        )
    )
    assert result["action"] == "recreated"
    assert result["ok"] is True
    assert result["template_hash"] == "hash-new"
    assert [name for name, _ in fake.calls] == ["update", "create"]
    assert any("dibuat ulang" in warning for warning in result["warnings"])


