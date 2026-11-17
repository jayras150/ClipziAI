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


def test_map_gpu_model_accepts_filesystem_path(tmp_path):
    from app.services.transcriber import AudioTranscriber

    model_dir = tmp_path / "whisper_model"
    model_dir.mkdir()
    assert AudioTranscriber._map_gpu_model(str(model_dir)) == str(model_dir)
    assert AudioTranscriber._map_gpu_model("openai/whisper-large-v3") == "large-v3"


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
