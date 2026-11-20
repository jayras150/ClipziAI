"""Regression test branding: normalisasi, validasi warna/url, fallback."""
from app.services.branding import DEFAULT_BRANDING, normalize_branding


def test_nama_app_wajib_ada():
    assert normalize_branding({"app_name": "   "})["app_name"] == DEFAULT_BRANDING["app_name"]
    assert normalize_branding({"app_name": "  Clipzy Pro  "})["app_name"] == "Clipzy Pro"


def test_warna_tidak_valid_dikembalikan_ke_default():
    assert normalize_branding({"accent_color": "red"})["accent_color"] == "#f4c76b"
    assert normalize_branding({"accent_color": "#00FF00"})["accent_color"] == "#00FF00"


def test_url_logo_harus_http_atau_relatif():
    assert normalize_branding({"logo_url": "ftp://x/logo.png"})["logo_url"] is None
    assert normalize_branding({"logo_url": "https://cdn/logo.png"})["logo_url"] == "https://cdn/logo.png"
    assert normalize_branding({"favicon_url": "/favicon.ico"})["favicon_url"] == "/favicon.ico"


def test_field_tidak_dikenal_diabaikan():
    cfg = normalize_branding({"app_name": "X", "is_admin": True})
    assert "is_admin" not in cfg


def test_presigned_url_aset_diubah_menjadi_path_api_permanen():
    """URL presigned storage kedaluwarsa (maks 7 hari) -> jangan disimpan apa adanya."""
    signed = (
        "https://files.example.r2.cloudflarestorage.com/clipzy/branding/hero/a.mp4"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=abc"
    )
    assert normalize_branding({"hero_video_url": signed})["hero_video_url"] == (
        "/api/branding/asset/branding/hero/a.mp4"
    )

    favicon_signed = "https://x/branding/favicon/icon32-1.png?X-Amz-Signature=q"
    cfg = normalize_branding({"favicon_url": favicon_signed})
    assert cfg["favicon_url"] == "/api/branding/asset/branding/favicon/icon32-1.png"
    assert cfg["favicons"]["icon32"] == "/api/branding/asset/branding/favicon/icon32-1.png"


def test_path_api_aset_dibiarkan():
    cfg = normalize_branding({"hero_video_url": "/api/branding/asset/branding/hero/a.mp4"})
    assert cfg["hero_video_url"] == "/api/branding/asset/branding/hero/a.mp4"


def test_endpoint_aset_branding_redirect(monkeypatch):
    import asyncio

    import pytest
    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse

    from app.api import branding as api_branding

    class DummyStorage:
        def get_presigned_url(self, key: str, expiration: int = 3600) -> str:
            assert key.startswith("branding/")
            return "https://cdn.example/" + key + "?sig=1"

    monkeypatch.setattr(api_branding, "get_storage", lambda: DummyStorage())
    response = asyncio.run(api_branding.public_branding_asset("branding/hero/a.mp4"))
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "https://cdn.example/branding/hero/a.mp4?sig=1"
    assert response.headers["cache-control"] == "public, max-age=1800"

    with pytest.raises(HTTPException):
        asyncio.run(api_branding.public_branding_asset("../secret"))


def test_endpoint_aset_branding_tanpa_storage(monkeypatch):
    import asyncio

    import pytest
    from fastapi import HTTPException

    from app.api import branding as api_branding

    def _boom():
        raise RuntimeError("storage belum dikonfigurasi")

    monkeypatch.setattr(api_branding, "get_storage", _boom)
    with pytest.raises(HTTPException):
        asyncio.run(api_branding.public_branding_asset("branding/logo/x.png"))


def test_upload_admin_menyimpan_path_api():
    from app.api.admin.branding import _branding_asset_url

    assert (
        _branding_asset_url("branding/hero/a.mp4")
        == "/api/branding/asset/branding/hero/a.mp4"
    )
