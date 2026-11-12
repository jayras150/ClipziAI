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
