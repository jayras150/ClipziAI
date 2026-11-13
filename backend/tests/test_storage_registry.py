"""
Test registry storage multi-provider (tanpa koneksi jaringan).
"""


def test_preset_provider_lengkap():
    from app.services.storage_registry import PROVIDERS

    for key in ("r2", "b2", "s3", "wasabi", "spaces", "supabase", "minio"):
        assert key in PROVIDERS
        assert PROVIDERS[key]["label"]
        assert "endpoint" in PROVIDERS[key]


def test_normalize_config_memilih_primary_dan_mirror():
    from app.services.storage_registry import normalize_config

    config = normalize_config(
        {
            "items": [
                {"id": "a", "provider": "r2", "bucket": "b1"},
                {"id": "b", "provider": "b2", "bucket": "b2"},
            ],
            "primary_id": "b",
            "mirror_ids": ["a", "tidak-ada"],
        }
    )
    assert config["primary_id"] == "b"
    assert config["mirror_ids"] == ["a"]


def test_normalize_config_primary_fallback_ke_item_pertama():
    from app.services.storage_registry import normalize_config

    config = normalize_config({"items": [{"id": "x", "bucket": "b"}], "primary_id": "zzz"})
    assert config["primary_id"] == "x"


def test_mask_kredensial():
    from app.services.storage_registry import mask

    assert mask("AKIAIOSFODNN7EXAMPLE") == "AKI***PLE"
    assert mask("abc") == "***"
    assert mask(None) is None


def test_public_view_tidak_membocorkan_secret():
    from app.core.security import encrypt_field
    from app.services.storage_registry import normalize_config, public_view

    config = normalize_config(
        {
            "items": [
                {
                    "id": "a",
                    "provider": "r2",
                    "bucket": "bucket-1",
                    "access_key_enc": encrypt_field("AKIATESTKEY123"),
                    "secret_key_enc": encrypt_field("SUPERSECRET"),
                }
            ],
            "primary_id": "a",
        }
    )
    view = public_view(config)
    item = view["items"][0]
    assert item["has_credentials"] is True
    assert "SUPERSECRET" not in str(view)
    assert "secret_key_enc" not in item
    assert item["access_key_masked"].startswith("AKI")


def test_public_view_menyertakan_provider_presets():
    from app.services.storage_registry import public_view

    view = public_view({"items": [], "primary_id": None, "mirror_ids": []})
    ids = [row["id"] for row in view["providers"]]
    assert "r2" in ids and "b2" in ids
