"""
Video Downloader Service - yt-dlp wrapper.

Cookies bersifat OPSIONAL. Sumber cookies dicari berurutan:
    1. argumen ``cookies_path`` pada method
    2. env ``YTDLP_COOKIES_FILE``    -> path ke file cookies.txt (format Netscape)
    3. env ``YTDLP_COOKIES_BASE64``  -> isi cookies.txt yang di-encode base64
Jika ketiganya kosong, yt-dlp berjalan tanpa cookies (cukup untuk video publik
dari IP residensial).

Cookies diperlukan ketika YouTube memblokir IP datacenter (Vast.ai/VPS) dengan
pesan "Sign in to confirm you're not a bot", atau untuk video age-restricted /
private / member-only.
"""
import asyncio
import base64
import binascii
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, cast

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

SUPPORTED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "facebook.com",
    "vimeo.com",
)


def _decode_cookies_base64(raw: str) -> str:
    """Decode base64 -> teks cookies.txt (format Netscape) dengan validasi."""
    cleaned = "".join(raw.split())
    padding = (-len(cleaned)) % 4

    try:
        decoded_bytes = base64.b64decode(cleaned + "=" * padding, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("YTDLP_COOKIES_BASE64 bukan base64 yang valid.") from exc

    try:
        text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Hasil decode cookies bukan teks UTF-8. Pastikan yang di-encode adalah "
            "file cookies.txt (format Netscape), bukan file biner."
        ) from exc

    if "Netscape HTTP Cookie File" not in text and "\t" not in text:
        raise ValueError(
            "Isi cookies tidak terlihat seperti cookies.txt format Netscape "
            "(harus baris tab-separated). Ekspor ulang dengan ekstensi "
            "'Get cookies.txt LOCALLY'."
        )
    return text


def _parse_extractor_args(raw: str) -> Dict[str, Dict[str, list]]:
    """Ubah "youtube:player_client=web_safari,android" jadi dict extractor_args.

    Grammar yt-dlp: ``extractor:key=value1,value2;extractor2:key=value``
    (spec dipisah ";" , nilai ganda dipisah ",").
    """
    result: Dict[str, Dict[str, list]] = {}
    for spec in raw.split(";"):
        spec = spec.strip()
        if not spec or ":" not in spec or "=" not in spec:
            continue

        extractor, _, rest = spec.partition(":")
        key, _, values = rest.partition("=")

        extractor = extractor.strip()
        key = key.strip()
        items = [item.strip() for item in values.split(",") if item.strip()]

        if extractor and key and items:
            result.setdefault(extractor, {})[key] = items

    return result


class VideoDownloader:
    """Download videos from YouTube, TikTok, Instagram, Facebook, Vimeo using yt-dlp."""

    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._cookiefile_cache: Optional[str] = None
        self._cookiefile_resolved = False

    def validate_url(self, url: str) -> bool:
        """Validate if URL is from a supported platform."""
        return any(domain in url for domain in SUPPORTED_DOMAINS)

    def detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        elif "tiktok.com" in url_lower:
            return "tiktok"
        elif "instagram.com" in url_lower:
            return "instagram"
        elif "facebook.com" in url_lower:
            return "facebook"
        elif "vimeo.com" in url_lower:
            return "vimeo"
        return "unknown"

    def detect_proactively(self, info: Mapping[str, Any]) -> str:
        """Detect platform from yt-dlp info dict."""
        extractor = info.get("extractor", "")
        if "youtube" in extractor:
            return "youtube"
        elif "tiktok" in extractor:
            return "tiktok"
        elif "instagram" in extractor:
            return "instagram"
        elif "facebook" in extractor:
            return "facebook"
        elif "vimeo" in extractor:
            return "vimeo"
        return "unknown"

    def _resolve_cookiefile(self, cookies_path: Optional[str] = None) -> Optional[str]:
        """Tentukan file cookies yang dipakai yt-dlp (lihat docstring modul)."""
        if cookies_path:
            if os.path.exists(cookies_path):
                return cookies_path
            logger.warning("cookies_path '%s' tidak ditemukan, diabaikan.", cookies_path)

        if self._cookiefile_resolved:
            return self._cookiefile_cache

        self._cookiefile_resolved = True

        explicit_file = (settings.YTDLP_COOKIES_FILE or "").strip()
        if explicit_file:
            if os.path.exists(explicit_file):
                self._cookiefile_cache = explicit_file
                logger.info("yt-dlp memakai cookies dari file: %s", explicit_file)
                return explicit_file
            logger.warning("YTDLP_COOKIES_FILE '%s' tidak ada, beralih ke base64.", explicit_file)

        encoded = (settings.YTDLP_COOKIES_BASE64 or "").strip()
        if not encoded:
            logger.info("yt-dlp berjalan tanpa cookies (YTDLP_COOKIES_* tidak diisi).")
            return None

        text = _decode_cookies_base64(encoded)

        cache_target = Path(settings.YTDLP_COOKIES_CACHE_PATH or "./.cache/ytdlp_cookies.txt")
        cache_target.parent.mkdir(parents=True, exist_ok=True)
        cache_target.write_text(text, encoding="utf-8")
        try:
            os.chmod(cache_target, 0o600)
        except OSError:  # Windows tidak mendukung chmod penuh
            pass

        self._cookiefile_cache = str(cache_target)
        logger.info("yt-dlp memakai cookies hasil decode base64: %s", cache_target)
        return self._cookiefile_cache

    def _base_ydl_opts(self, cookies_path: Optional[str] = None) -> Dict[str, Any]:
        """Opsi dasar yt-dlp: quiet, cookies, proxy, extractor_args."""
        opts: Dict[str, Any] = {"quiet": True, "no_warnings": True}

        cookiefile = self._resolve_cookiefile(cookies_path)
        if cookiefile:
            opts["cookiefile"] = cookiefile

        if settings.YTDLP_PROXY:
            opts["proxy"] = settings.YTDLP_PROXY

        if settings.YTDLP_EXTRACTOR_ARGS:
            extractor_args = _parse_extractor_args(settings.YTDLP_EXTRACTOR_ARGS)
            if extractor_args:
                opts["extractor_args"] = extractor_args

        return opts

    async def get_video_info(self, url: str, cookies_path: Optional[str] = None) -> Dict[str, Any]:
        """Get video metadata without downloading."""
        ydl_opts = self._base_ydl_opts(cookies_path)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_info, url, ydl_opts)

    async def download_video(
        self,
        url: str,
        output_filename: str,
        cookies_path: Optional[str] = None,
        quality: str = "720",
    ) -> str:
        """Download video and return local file path."""
        output_path = str(self.download_dir / output_filename)

        ydl_opts = self._base_ydl_opts(cookies_path)
        ydl_opts.update(
            {
                "format": f"bestvideo[height<={quality}]+bestaudio/best",
                "merge_output_format": "mp4",
                # WAJIB pakai %(ext)s: untuk URL file langsung (mis. .mp4 di R2/CDN)
                # yt-dlp menyimpan dengan nama apa adanya TANPA ekstensi, sehingga
                # pencarian `source.mp4` gagal dan langkah ffprobe berikutnya error.
                "outtmpl": f"{output_path}.%(ext)s",
                "retries": 3,
                "fragment_retries": 3,
            }
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download, url, ydl_opts)

        # Cari file hasil unduhan: nama dengan ekstensi, atau nama tanpa ekstensi
        # (kasus URL file langsung).
        candidates = [f"{self.download_dir / output_filename}.{ext}" for ext in ("mp4", "mkv", "webm")]
        candidates.append(str(self.download_dir / output_filename))
        for path in candidates:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                if not Path(path).suffix:
                    # Beri ekstensi .mp4 agar konsisten untuk langkah berikutnya.
                    renamed = f"{path}.mp4"
                    try:
                        os.replace(path, renamed)
                        return renamed
                    except OSError:
                        return path
                return path
        # Jangan kembalikan path yang belum tentu ada: kegagalan unduh harus
        # terlihat jelas di sini, bukan muncul sebagai error ffprobe di langkah
        # berikutnya.
        try:
            files = sorted(os.listdir(self.download_dir))[:10]
        except OSError:
            files = []
        raise RuntimeError(
            "unduhan tidak menghasilkan file video "
            f"(url={url}, folder={self.download_dir}, isi={files})"
        )

    def _extract_info(self, url: str, ydl_opts: dict) -> Dict[str, Any]:
        import yt_dlp

        # yt-dlp mengetik parameter sebagai TypedDict (`_Params`) yang sangat
        # sempit; cast agar type checker tidak salah tuduh pada dict dinamis.
        with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise RuntimeError(f"yt-dlp tidak mengembalikan info untuk: {url}")
            return {
                "title": info.get("title"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "platform": self.detect_proactively(info),
                "thumbnail": info.get("thumbnail"),
            }

    def _download(self, url: str, ydl_opts: dict):
        import yt_dlp

        with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
            ydl.download([url])

