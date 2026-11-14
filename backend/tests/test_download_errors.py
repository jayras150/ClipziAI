"""Unit test klasifikasi error downloader + pesan aman user."""
import pytest

from app.services import download_errors as de


def test_classify_bot_check():
    text = "ERROR: [youtube] x: Sign in to confirm you're not a bot."
    assert de.classify_download_error(text) == de.CATEGORY_BOT_CHECK
    assert de.is_retryable(de.CATEGORY_BOT_CHECK) is True


def test_classify_permanent_errors():
    assert de.classify_download_error("Private video") == de.CATEGORY_VIDEO_PRIVATE
    assert de.classify_download_error("Video unavailable") == de.CATEGORY_VIDEO_UNAVAILABLE
    assert de.classify_download_error("Unsupported URL") == de.CATEGORY_INVALID_URL
    for category in (
        de.CATEGORY_VIDEO_PRIVATE,
        de.CATEGORY_VIDEO_UNAVAILABLE,
        de.CATEGORY_INVALID_URL,
        de.CATEGORY_COOKIES_INVALID,
    ):
        assert de.is_retryable(category) is False


def test_cookies_invalid_detected():
    assert (
        de.classify_download_error("Cookies are no longer valid. Please sign in again.")
        == de.CATEGORY_COOKIES_INVALID
    )


def test_user_message_never_leaks_technical_details():
    forbidden = ("downloaderror", "traceback", "http 403", "http 429", "yt-dlp", "cookie")
    for category in (
        de.CATEGORY_BOT_CHECK,
        de.CATEGORY_COOKIES_MISSING,
        de.CATEGORY_VIDEO_PRIVATE,
        de.CATEGORY_VIDEO_UNAVAILABLE,
        de.CATEGORY_INVALID_URL,
        de.CATEGORY_UNKNOWN,
    ):
        message = de.user_message_for(category).lower()
        assert "video" in message or "link" in message
        for word in forbidden:
            assert word not in message


def test_user_messages_are_english_only():
    """UI user wajib bahasa Inggris; jangan ada sisa kata Indonesia."""
    banned = (
        "silakan",
        "gagal",
        "tidak",
        "belum",
        "periksa",
        "hubungi",
        "coba",
        "video ini",
        "pastikan",
        "kembali",
        "bermasalah",
    )
    categories = (
        de.CATEGORY_BOT_CHECK,
        de.CATEGORY_COOKIES_INVALID,
        de.CATEGORY_COOKIES_MISSING,
        de.CATEGORY_VIDEO_PRIVATE,
        de.CATEGORY_VIDEO_UNAVAILABLE,
        de.CATEGORY_INVALID_URL,
        de.CATEGORY_GEO_BLOCKED,
        de.CATEGORY_RATE_LIMITED,
        de.CATEGORY_FORMAT_UNAVAILABLE,
        de.CATEGORY_NETWORK,
        de.CATEGORY_TIMEOUT,
        de.CATEGORY_UNKNOWN,
    )
    for category in categories:
        message = de.user_message_for(category).lower()
        for word in banned:
            assert word not in message, f"{category}: masih ada kata '{word}'"
        assert "video" in message or "link" in message


def test_download_error_exposes_metadata():
    err = de.DownloadError(
        "sign in to confirm you're not a bot",
        attempts=[{"label": "fmt=b cookies=no"}],
        ytdlp_version="2026.10.26",
        cookie_id="abc",
        cookie_used=False,
        http_status=403,
    )
    assert err.category == de.CATEGORY_BOT_CHECK
    assert err.retryable is True
    assert err.attempts and err.ytdlp_version == "2026.10.26"
    assert err.http_status == 403
    assert "downloaderror" not in err.user_message.lower()


def test_http_status_extraction():
    assert de.http_status_from("DownloadError: HTTP Error 403: Forbidden") == 403
    assert de.http_status_from("429 Too Many Requests") == 429
    assert de.http_status_from("no code here") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Requested format is not available", "format_unavailable"),
        ("timed out", "timeout"),
        ("Temporary failure in name resolution", "network"),
    ],
)
def test_misc_categories(text, expected):
    assert de.classify_download_error(text) == expected
