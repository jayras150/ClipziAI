"""
Klasifikasi error downloader (yt-dlp) + pesan aman untuk user.

Semua detail teknis (DownloadError, HTTP 403/429, traceback, perintah yt-dlp)
HANYA boleh muncul di log admin (`download_attempts`), tidak pernah di UI user.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Kategori yang dipakai di DB (kolom tasks.error_category / download_attempts).
CATEGORY_BOT_CHECK = "bot_check"
CATEGORY_COOKIES_INVALID = "cookies_invalid"
CATEGORY_COOKIES_MISSING = "cookies_missing"
CATEGORY_VIDEO_PRIVATE = "video_private"
CATEGORY_VIDEO_UNAVAILABLE = "video_unavailable"
CATEGORY_INVALID_URL = "invalid_url"
CATEGORY_GEO_BLOCKED = "geo_blocked"
CATEGORY_RATE_LIMITED = "rate_limited"
CATEGORY_FORMAT_UNAVAILABLE = "format_unavailable"
CATEGORY_NETWORK = "network"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_UNKNOWN = "unknown"

_USER_MESSAGE = (
    "Video gagal diproses.\n\n"
    "Terjadi kendala saat mengunduh video.\n"
    "Silakan coba kembali."
)

_BY_CATEGORY_MESSAGE = {
    CATEGORY_VIDEO_PRIVATE: (
        "Video ini bersifat privat atau dibatasi.\n\n"
        "Pastikan video dapat diakses publik, lalu coba kembali."
    ),
    CATEGORY_VIDEO_UNAVAILABLE: (
        "Video tidak tersedia atau sudah dihapus.\n\n"
        "Periksa kembali link videonya."
    ),
    CATEGORY_INVALID_URL: (
        "Link video tidak valid.\n\n"
        "Periksa kembali URL yang Anda masukkan."
    ),
    CATEGORY_COOKIES_MISSING: (
        "Video gagal diproses.\n\n"
        "Server belum memiliki akses yang diperlukan untuk mengunduh video ini.\n"
        "Silakan hubungi admin atau coba kembali nanti."
    ),
    CATEGORY_COOKIES_INVALID: (
        "Video gagal diproses.\n\n"
        "Akses ke video ini sedang bermasalah di server.\n"
        "Silakan coba kembali nanti."
    ),
    CATEGORY_GEO_BLOCKED: (
        "Video ini tidak dapat diakses dari lokasi server.\n\n"
        "Silakan coba video lain."
    ),
}

# Retry otomatis hanya untuk kegagalan sementara.
_RETRYABLE = {
    CATEGORY_BOT_CHECK,
    CATEGORY_RATE_LIMITED,
    CATEGORY_NETWORK,
    CATEGORY_TIMEOUT,
    CATEGORY_FORMAT_UNAVAILABLE,
    CATEGORY_UNKNOWN,
}


def classify_download_error(text: Optional[str]) -> str:
    """Tentukan kategori dari pesan error yt-dlp (lowercase matching)."""
    lowered = (text or "").lower()
    if not lowered:
        return CATEGORY_UNKNOWN

    if "unsupported url" in lowered or "is not a valid url" in lowered:
        return CATEGORY_INVALID_URL
    if "private video" in lowered or "video is private" in lowered:
        return CATEGORY_VIDEO_PRIVATE
    if (
        "video unavailable" in lowered
        or "has been removed" in lowered
        or "does not exist" in lowered
        or "account associated with this video has been terminated" in lowered
    ):
        return CATEGORY_VIDEO_UNAVAILABLE
    if "not available in your country" in lowered or "geo" in lowered and "block" in lowered:
        return CATEGORY_GEO_BLOCKED
    if "sign in to confirm" in lowered or "not a bot" in lowered:
        return CATEGORY_BOT_CHECK
    if (
        "cookies are no longer valid" in lowered
        or "login required" in lowered
        or "please sign in" in lowered
        or "account has been terminated" in lowered
    ):
        return CATEGORY_COOKIES_INVALID
    if "429" in lowered or "too many requests" in lowered:
        return CATEGORY_RATE_LIMITED
    if "requested format is not available" in lowered or "no video formats" in lowered:
        return CATEGORY_FORMAT_UNAVAILABLE
    if "timed out" in lowered or "timeout" in lowered:
        return CATEGORY_TIMEOUT
    if any(
        marker in lowered
        for marker in (
            "connection",
            "temporary failure",
            "name or service not known",
            "ssl",
            "network is unreachable",
            "connection reset",
        )
    ):
        return CATEGORY_NETWORK
    return CATEGORY_UNKNOWN


def user_message_for(category: Optional[str]) -> str:
    """Pesan yang aman ditampilkan ke user (tanpa detail teknis)."""
    return _BY_CATEGORY_MESSAGE.get(category or "", _USER_MESSAGE)


def is_retryable(category: Optional[str]) -> bool:
    return (category or CATEGORY_UNKNOWN) in _RETRYABLE


class RunnerFallbackQueued(Exception):
    """Sinyal internal: task dipindahkan ke runner fallback, bukan error."""


def http_status_from(text: Optional[str]) -> Optional[int]:
    """Ambil kode HTTP dari pesan yt-dlp (mis. 'HTTP Error 403')."""
    import re

    match = re.search(r"http error (\d{3})|\b(4\d{2}|5\d{2})\b", (text or "").lower())
    if not match:
        return None
    value = match.group(1) or match.group(2)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class DownloadError(RuntimeError):
    """Kegagalan download dengan metadata terstruktur untuk log admin."""

    def __init__(
        self,
        message: str,
        *,
        category: Optional[str] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
        ytdlp_version: Optional[str] = None,
        cookie_id: Optional[str] = None,
        cookie_used: bool = False,
        http_status: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.category = category or classify_download_error(message)
        self.attempts = attempts or []
        self.ytdlp_version = ytdlp_version
        self.cookie_id = cookie_id
        self.cookie_used = cookie_used
        self.http_status = http_status
        self.user_message = user_message_for(self.category)
        self.retryable = is_retryable(self.category)
