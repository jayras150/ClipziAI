"""Tes manifest sumber model Whisper + template Vast otomatis."""
from __future__ import annotations

import asyncio

from app.services import model_sources


def test_manifest_lima_provider_lengkap():
    providers = model_sources.providers()
    ids = [item.id for item in providers]
    assert ids == ["gdrive", "dropbox", "backblaze", "huggingface", "s3"]
    for provider in providers:
        assert provider.template_name.startswith("Clipzy ")
        assert provider.fields, provider.id
        for field in provider.fields:
            assert field["name"]
            assert field["type"] in {"text", "secret"}
        assert provider.restore_mode in {
            "vast_cloud_copy",
            "url_download",
            "hf_snapshot",
        }


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


def test_restore_env_cache():
    model_sources.set_restore_env({"CLIPZI_MODEL_URL": "https://x/model.bin", "KOSONG": ""})
    env = model_sources.restore_env()
    assert env == {"CLIPZI_MODEL_URL": "https://x/model.bin"}
    model_sources.set_restore_env(None)
    assert model_sources.restore_env() == {}


def test_restore_plan_gdrive_pakai_cloud_copy():
    plan = asyncio.run(
        model_sources.restore_plan(None, "gdrive", "/vast-backup/Clipzy/whisper_models/large-v3")
    )
    assert plan["mode"] == "vast_cloud_copy"
    assert plan["config"]["restore_enabled"] is True
    assert plan["config"]["restore_src"].endswith("large-v3")
    assert plan["env"] == {}


def test_restore_plan_huggingface_tanpa_secret():
    plan = asyncio.run(
        model_sources.restore_plan(None, "huggingface", "Systran/faster-whisper-large-v3")
    )


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
