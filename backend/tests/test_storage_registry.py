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


def test_url_publik_dipakai_bila_bisa_diakses(monkeypatch):
    from app.services import storage_registry as reg

    monkeypatch.setattr(reg, "_public_reachable", lambda resolved, url: True)

    class _Client:
        def generate_presigned_url(self, *a, **k):  # pragma: no cover
            return "presigned"

    resolved = reg.ResolvedStorage(
        item={"id": "p1"},
        client=_Client(),
        bucket="files",
        public_domain="https://pub.example",
        path_prefix="",
    )
    service = reg.StorageService()
    assert service._url(resolved, "clips/a.mp4") == "https://pub.example/clips/a.mp4"


def test_url_presigned_dipakai_bila_bucket_privat(monkeypatch):
    """r2.dev menolak (403) => URL harus presigned, bukan tautan mati."""
    from app.services import storage_registry as reg

    monkeypatch.setattr(reg, "_public_reachable", lambda resolved, url: False)

    class _Client:
        def generate_presigned_url(self, *args, **kwargs):
            return "https://presigned/x.mp4?sign=abc"

    resolved = reg.ResolvedStorage(
        item={"id": "p1"},
        client=_Client(),
        bucket="files",
        public_domain="https://pub.example",
        path_prefix="",
    )
    service = reg.StorageService()
    url = service._url(resolved, "clips/a.mp4")
    assert url.startswith("https://presigned/")
    assert "pub.example" not in url


def test_public_url_reachable_false_saat_403(monkeypatch):
    from app.services import storage_registry as reg

    class _Denied:
        status = 403

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(*_a, **_k):
        raise reg.urllib.error.HTTPError("u", 403, "Forbidden", {}, None)  # type: ignore[attr-defined]

    monkeypatch.setattr(reg.urllib.request, "urlopen", fake_urlopen)
    assert reg.public_url_reachable("https://pub.example/x") is False

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


def test_get_storage_di_dalam_event_loop_tetap_memuat(monkeypatch):
    """Pipeline async: loading lewat thread, bukan `asyncio.run()` di loop aktif."""
    import asyncio

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

    async def pipeline():
        return reg.get_storage().primary_id

    assert asyncio.run(pipeline()) == "p1"
    assert calls["n"] == 1


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


def test_normalize_domain_membersihkan_url():
    from app.services.storage_registry import normalize_domain

    assert normalize_domain("https://CDN.ProxyAI.live/path") == "cdn.proxyai.live"
    assert normalize_domain(" cdn.proxyai.live ") == "cdn.proxyai.live"
    assert normalize_domain("") == ""


def test_custom_domain_target_r2():
    from app.services.storage_registry import custom_domain_target

    item = {
        "provider": "r2",
        "bucket": "files",
        "endpoint": "https://d7a75c6cd293f2fa36cba8c5a403c035.r2.cloudflarestorage.com",
    }
    assert (
        custom_domain_target(item)
        == "files.d7a75c6cd293f2fa36cba8c5a403c035.r2.cloudflarestorage.com"
    )
    assert custom_domain_target({"provider": "b2", "bucket": "x"}) is None


def test_check_custom_domain_format_salah():
    from app.services.storage_registry import check_custom_domain

    result = check_custom_domain("bukan domain", None)
    assert result["dns_ok"] is False
    assert result["hint"]
