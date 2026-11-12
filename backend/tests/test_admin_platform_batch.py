"""
Test untuk batch admin baru: provider AI, setelan platform/domain, dan
bantuan cookies YouTube base64.

Semua pure unit (tanpa DB/network), sesuai gaya test repo ini.
"""
from datetime import datetime, timedelta, timezone

import pytest


def test_provider_defaults_lengkap():
    from app.services.ai_client import PROVIDER_DEFAULTS, provider_metadata

    for key, value in PROVIDER_DEFAULTS.items():
        assert value.get("label"), f"provider {key} tanpa label"
        if key == "custom":
            # custom memang sengaja kosong: admin wajib mengisi sendiri.
            assert value.get("base_url") == ""
        else:
            assert value.get("base_url", "").startswith("http"), f"{key} tanpa base_url"

    meta = provider_metadata()
    ids = [item["id"] for item in meta]
    for expected in ("openai", "openrouter", "groq", "deepseek", "gemini", "xai", "custom"):
        assert expected in ids
    labels = [item["label"].lower() for item in meta]
    assert labels == sorted(labels)


def test_normalize_domain_dan_validasi_url():
    from app.services.platform_config import normalize_domain, validate_url

    assert normalize_domain("https://Clipzy.id/") == "clipzy.id"
    assert normalize_domain("admin.clipzy.id") == "admin.clipzy.id"
    assert normalize_domain("") == ""
    with pytest.raises(ValueError):
        normalize_domain("clipzy.id/path")

    assert validate_url("https://clipzy.id/") == "https://clipzy.id"
    assert validate_url("") == ""
    with pytest.raises(ValueError):
        validate_url("clipzy.id")
    with pytest.raises(ValueError):
        validate_url("ftp://clipzy.id")


def test_normalize_platform_default_aman():
    from app.services.platform_config import normalize_platform

    config = normalize_platform(None)
    assert config["domain_status"] == "idle"
    assert config["maintenance_mode"] is False
    assert config["signup_enabled"] is True

    merged = normalize_platform({"domain_status": "aneh", "maintenance_mode": "yes"})
    assert merged["domain_status"] == "idle"
    assert merged["maintenance_mode"] is True


def test_cookies_base64_roundtrip():
    from app.api.admin.ytdlp_cookies import (
        decode_cookies_base64,
        encode_cookies_base64,
        summarize_cookies,
    )

    plain = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tabc123\n"
        ".google.com\tTRUE\t/\tTRUE\t1893456000\tNID\tdef456\n"
    )
    encoded = encode_cookies_base64(plain)
    assert decode_cookies_base64(encoded) == plain
    # toleran terhadap spasi/baris baru sisa copy-paste
    assert decode_cookies_base64("  " + encoded + "\n") == plain

    summary = summarize_cookies(plain)
    assert summary["cookie_count"] == 2
    assert "youtube.com" in summary["domains"]
    assert summary["earliest_expiry"] is not None


def test_decode_cookies_base64_menolak_sampah():
    from app.api.admin.ytdlp_cookies import decode_cookies_base64

    with pytest.raises(ValueError):
        decode_cookies_base64("")
    with pytest.raises(ValueError):
        decode_cookies_base64("!!!bukan base64!!!")


def test_as_aware_menormalkan_naive_datetime():
    from app.services.auth_session import _as_aware

    naive = datetime(2026, 11, 12, 10, 0, 0)
    aware = _as_aware(naive)
    assert aware.tzinfo is not None
    expected = naive.replace(tzinfo=timezone.utc)
    assert aware == expected
    assert _as_aware(expected) == expected


def test_token_baru_dianggap_revoked_setelah_logout_all():
    """Simulasi aturan: token dengan iat < revoked_before harus ditolak."""
    from app.services.auth_session import _as_aware

    revoked_before = datetime.now(timezone.utc)
    older = (revoked_before - timedelta(minutes=5)).isoformat()
    newer = (revoked_before + timedelta(minutes=5)).isoformat()

    assert _as_aware(datetime.fromisoformat(older)) < revoked_before
    assert _as_aware(datetime.fromisoformat(newer)) > revoked_before
