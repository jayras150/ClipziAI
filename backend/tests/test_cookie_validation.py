"""Validasi cookie YouTube (format + kelengkapan auth) & klasifikasi expiry."""
import pytest

from app.services import cookie_store


HEADER = "# Netscape HTTP Cookie File\n"


def _line(name: str) -> str:
    return f".youtube.com\tTRUE\t/\tTRUE\t0\t{name}\tvalue\n"


def test_complete_cookie_accepted():
    text = HEADER + _line("SID") + _line("HSID") + _line("__Secure-3PSID")
    cookie_store.validate_cookies_text(text)


def test_incomplete_secure3_only_rejected():
    text = HEADER + _line("__Secure-3PSID") + _line("__Secure-3PSIDTS")
    with pytest.raises(ValueError) as exc:
        cookie_store.validate_cookies_text(text)
    assert "tidak lengkap" in str(exc.value)


def test_non_youtube_rejected():
    with pytest.raises(ValueError):
        cookie_store.validate_cookies_text(HEADER + ".example.com\tTRUE\t/\tTRUE\t0\tSID\tx\n")


def test_bot_check_does_not_look_expired():
    text = "Sign in to confirm you're not a bot"
    assert cookie_store.looks_like_bot_check(text) is True
    assert cookie_store.looks_expired(text) is False


def test_cookie_invalid_marker_looks_expired():
    assert cookie_store.looks_expired("Cookies are no longer valid") is True


def test_pick_cookie_is_random_and_empty_safe(monkeypatch):
    """Pool memilih acak (bukan selalu indeks pertama) dan aman saat kosong."""
    first, second, third = object(), object(), object()
    monkeypatch.setattr(cookie_store.random, "choice", lambda seq: seq[2])
    assert cookie_store.pick_cookie([first, second, third]) is third
    assert cookie_store.pick_cookie([]) is None


def test_encode_decode_base64_roundtrip():
    """Base64 dari menu admin harus bisa didecode kembali persis."""
    from app.api.admin.ytdlp_cookies import decode_cookies_base64, encode_cookies_base64

    text = HEADER + _line("SID") + _line("HSID") + _line("SAPISID")
    encoded = encode_cookies_base64(text)
    assert decode_cookies_base64(encoded) == text
    assert decode_cookies_base64(f"data:text/plain;base64,{encoded}") == text
