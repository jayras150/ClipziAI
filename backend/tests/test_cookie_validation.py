"""Tes validasi cookies YouTube (domain scope + sesi login).

Konteks: cookie SID/__Secure-1PSID/LOGIN_INFO adalah cookie akun Google yang
ditanam pada scope `.youtube.com`. Validator TIDAK boleh mewajibkan entri
`.google.com` — yt-dlp hanya mengirim cookie untuk host youtube.com.
"""
import pytest

from app.services.cookie_store import normalize_cookie_text, validate_cookies_text

HEADER = "# Netscape HTTP Cookie File\n"


def _line(domain: str, name: str, value: str = "x") -> str:
    return f"{domain}\tTRUE\t/\tTRUE\t1829446529\t{name}\t{value}"


def _text(*rows: str) -> str:
    return HEADER + "\n".join(rows) + "\n"


def test_youtube_only_dengan_sesi_login_diterima():
    text = _text(
        _line(".youtube.com", "SID"),
        _line(".youtube.com", "HSID"),
        _line(".youtube.com", "SSID"),
        _line(".youtube.com", "LOGIN_INFO"),
    )
    validate_cookies_text(text)  # tidak boleh raise


def test_google_domain_dibuang_saat_normalisasi():
    text = _text(
        _line(".google.com", "SID"),
        _line(".google.com", "HSID"),
        _line(".youtube.com", "__Secure-1PSID"),
    )
    normalized, dropped = normalize_cookie_text(text)
    assert dropped == 2
    assert ".google.com" not in normalized
    assert "youtube.com" in normalized
    validate_cookies_text(normalized)


def test_hanya_cookie_guest_ditolak():
    text = _text(
        _line(".youtube.com", "YSC"),
        _line(".youtube.com", "VISITOR_INFO1_LIVE"),
        _line(".youtube.com", "PREF"),
    )
    with pytest.raises(ValueError) as exc:
        validate_cookies_text(text)
    assert "belum login" in str(exc.value).lower()


def test_cookie_pendukung_saja_ditolak():
    text = _text(
        _line(".youtube.com", "SAPISID"),
        _line(".youtube.com", "HSID"),
        _line(".youtube.com", "__Secure-3PSIDTS"),
    )
    with pytest.raises(ValueError) as exc:
        validate_cookies_text(text)
    assert "tidak lengkap" in str(exc.value).lower()


def test_domain_non_youtube_ditolak():
    text = _text(_line(".tiktok.com", "sessionid"))
    with pytest.raises(ValueError) as exc:
        validate_cookies_text(text)
    assert "youtube.com" in str(exc.value)
