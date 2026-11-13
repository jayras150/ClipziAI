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


def test_get_storage_memuat_konfigurasi_bila_cache_kosong(monkeypatch):
    """Worker: `get_storage()` wajib lazy-load konfigurasi.

    Regresi: dulu worker tidak pernah memanggil `load_storage_config()` (hanya
    startup FastAPI), sehingga cache kosong dan semua upload gagal dengan pesan
    "storage belum dikonfigurasi (Settings > Storage)".
    """
    from app.services import storage_registry as reg

    monkeypatch.setattr(reg, "_config", dict(reg.DEFAULT_STORAGE))
    calls = {"n": 0}

    async def fake_load():
        calls["n"] += 1
        return reg.set_config(
            {
                "primary_id": "p1",
                "mirror_ids": [],
                "items": [
                    {
                        "id": "p1",
                        "name": "uji",
                        "provider": "r2",
                        "bucket": "b",
                        "endpoint": "https://x",
                        "region": "auto",
                        "access_key_enc": "x",
                        "secret_key_enc": "y",
                        "enabled": True,
                    }
                ],
            }
        )

    monkeypatch.setattr(reg, "load_storage_config", fake_load)

    service = reg.get_storage()

    assert calls["n"] == 1
    assert service.primary_id == "p1"
    assert len(service.items) == 1


def test_get_storage_tidak_memuat_ulang_bila_sudah_terisi(monkeypatch):
    from app.services import storage_registry as reg

    monkeypatch.setattr(
        reg,
        "_config",
        reg.normalize_config(
            {
                "primary_id": "p1",
                "items": [
                    {
                        "id": "p1",
                        "name": "uji",
                        "provider": "r2",
                        "bucket": "b",
                        "endpoint": "https://x",
                        "region": "auto",
                        "access_key_enc": "x",
                        "secret_key_enc": "y",
                        "enabled": True,
                    }
                ],
            }
        ),
    )
    calls = {"n": 0}

    async def fake_load():  # pragma: no cover - tidak boleh terpanggil
        calls["n"] += 1
        return {}

    monkeypatch.setattr(reg, "load_storage_config", fake_load)

    reg.get_storage()
    assert calls["n"] == 0
