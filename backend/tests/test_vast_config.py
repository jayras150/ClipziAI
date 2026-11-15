"""Tes config Vast.ai (DB>ENV), env worker, dan normalisasi billing."""
import asyncio

import pytest

from app.services import vast_admin, vast_config


def test_normalize_vast_clamps_and_allowlist():
    cfg = vast_config.normalize_vast(
        {
            "worker_disk": 9999,
            "max_workers": 0,
            "dispatch_mode": "AUTO",
            "gpu_allowlist": "RTX 4090, rtx_4090 ,A100",
            "target_util": 3,
            "api_key_enc": None,
        }
    )
    assert cfg["worker_disk"] == 500
    assert cfg["max_workers"] == 1
    assert cfg["dispatch_mode"] == ""
    assert cfg["gpu_allowlist"] == ["RTX 4090", "A100"]
    assert cfg["target_util"] == 1.0
    assert cfg["api_key_enc"] == ""


def test_mask_and_validate_key():
    assert vast_config.mask_api_key("") == ""
    assert vast_config.mask_api_key("abcdef1234567890") == "****7890"
    with pytest.raises(ValueError):
        vast_config.validate_vast_key("https://console.vast.ai")
    with pytest.raises(ValueError):
        vast_config.validate_vast_key("short")


def test_public_config_never_exposes_key(monkeypatch):
    monkeypatch.setattr(
        vast_config, "decrypt_field", lambda value: "abcdef1234567890"
    )
    cfg = vast_config.normalize_vast(
        {
            "worker_image": "img:worker",
            "api_key_enc": "enc-value",
            "max_workers": 2,
        }
    )
    cfg["_api_key_source"] = "db"
    cfg["_sources"] = {"max_workers": "db"}
    public = vast_config.public_vast_config(cfg)
    assert "api_key_enc" not in public
    assert public["api_key_masked"] == "****7890"
    assert public["max_workers"] == 2
    assert public["sources"]["max_workers"] == "db"


def test_get_config_prefers_db(monkeypatch):
    stored = {
        "max_workers": 3,
        "worker_disk": 80,
        "gpu_allowlist": ["RTX 4090"],
        "api_key_enc": "",
    }

    async def fake_get(db, key, default=None):
        return stored

    from app.services import platform_settings as ps

    monkeypatch.setattr(ps, "get_setting", fake_get)
    cfg = asyncio.run(vast_config.get_vast_config(object()))
    assert cfg["max_workers"] == 3
    assert cfg["worker_disk"] == 80
    assert cfg["gpu_allowlist"] == ["RTX 4090"]
    assert cfg["_sources"]["max_workers"] == "db"


def test_env_spec_masks_secrets_and_export(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "DATABASE_URL", "postgresql://user:pass@host/db")
    spec = {item["name"]: item for item in vast_admin.worker_env_spec()}
    assert "DATABASE_URL" in spec
    assert spec["DATABASE_URL"]["secret"] is True
    assert spec["DATABASE_URL"]["preview"].startswith("****")

    masked = vast_admin.env_text(reveal=False)
    assert "DATABASE_URL=****" in masked
    revealed = vast_admin.env_text(reveal=True)
    assert "postgresql://user:pass@host/db" in revealed


def test_normalize_restore_fields():
    cfg = vast_config.normalize_vast(
        {
            "restore_enabled": "true",
            "restore_timeout": 9999,
            "restore_connection": "47129",
            "restore_src": "/vast-backup/Clipzy/whisper_model",
            "restore_model_path": "/workspace/whisper_model",
        }
    )
    assert cfg["restore_enabled"] is True
    assert cfg["restore_timeout"] == 3600
    assert cfg["restore_connection"] == "47129"
    assert cfg["restore_model_path"] == "/workspace/whisper_model"


def test_pick_connection_prefers_saved_valid_id():
    from app.services.vast_worker import pick_connection_id

    rows = [
        {"id": "47129", "name": "gdrive-sujinwo555"},
        {"id": "999", "name": "other-drive"},
    ]
    assert pick_connection_id(rows, "47129") == "47129"


def test_pick_connection_auto_uses_single_connection():
    from app.services.vast_worker import pick_connection_id

    rows = [{"id": "47129", "name": "gdrive-sujinwo555"}]
    assert pick_connection_id(rows, "47108") == "47129"
    assert pick_connection_id(rows, "") == "47129"


def test_pick_connection_uses_unique_drive_when_multiple():
    from app.services.vast_worker import pick_connection_id

    rows = [
        {"id": "1", "name": "s3-archive"},
        {"id": "47129", "name": "gdrive-sujinwo555"},
    ]
    assert pick_connection_id(rows, "47108") == "47129"


def test_pick_connection_refuses_ambiguous_account():
    from app.services.vast_worker import pick_connection_id

    rows = [
        {"id": "1", "name": "gdrive-a"},
        {"id": "2", "name": "gdrive-b"},
    ]
    with pytest.raises(RuntimeError):
        pick_connection_id(rows, "47108")


def test_pick_connection_refuses_empty_account():
    from app.services.vast_worker import pick_connection_id

    with pytest.raises(RuntimeError):
        pick_connection_id([], "47108")



def test_map_gpu_model_accepts_filesystem_path(tmp_path):
    from app.services.transcriber import AudioTranscriber

    model_dir = tmp_path / "whisper_model"
    model_dir.mkdir()
    assert AudioTranscriber._map_gpu_model(str(model_dir)) == str(model_dir)
    assert AudioTranscriber._map_gpu_model("openai/whisper-large-v3") == "large-v3"


def test_worker_env_uses_restored_model(monkeypatch):
    from app.core.config import get_settings
    from app.services.vast_worker import build_worker_env

    settings = get_settings()
    original = (
        settings.VAST_RESTORE_ENABLED,
        settings.VAST_RESTORE_TIMEOUT,
        settings.VAST_RESTORE_MODEL_PATH,
        settings.GPU_WHISPER_MODEL,
    )
    try:
        settings.VAST_RESTORE_ENABLED = True
        settings.VAST_RESTORE_TIMEOUT = 900
        settings.VAST_RESTORE_MODEL_PATH = "/workspace/whisper_model"
        settings.GPU_WHISPER_MODEL = "large-v3"
        env = build_worker_env()
    finally:
        (
            settings.VAST_RESTORE_ENABLED,
            settings.VAST_RESTORE_TIMEOUT,
            settings.VAST_RESTORE_MODEL_PATH,
            settings.GPU_WHISPER_MODEL,
        ) = original

    assert env["CLIPZI_RESTORE_TIMEOUT"] == "900"
    assert env["CLIPZI_RESTORE_MODEL_PATH"] == "/workspace/whisper_model"
    assert env["GPU_WHISPER_MODEL"] == "/workspace/whisper_model"


def test_invoice_normalization_sorted():
    rows = vast_admin._normalize_invoices(
        [
            {"timestamp": 1700000000, "amount": "0.5", "type": "charge"},
            {"timestamp": 1800000000, "amount": "-1.5", "type": "credit"},
        ]
    )
    assert rows[0]["type"] == "credit"
    assert rows[0]["amount"] == -1.5
    assert rows[1]["timestamp"].startswith("2023-11-14")
