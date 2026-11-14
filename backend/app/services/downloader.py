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
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, cast

from app.core.config import get_settings
from app.services.download_errors import (
    CATEGORY_COOKIES_MISSING,
    DownloadError,
    classify_download_error,
    http_status_from,
)

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


def format_ladder(height: int) -> list[str]:
    """
    Urutan selector format yang dicoba sampai berhasil.

    Kenapa berlapis: selector lama `bestvideo[height<=720]+bestaudio/best` gagal
    dengan pesan "Requested format is not available" ketika YouTube (sering pada
    IP datacenter) hanya menyediakan *video-only*, hanya *combined*, atau hanya
    format DASH tertentu. `bv*` menerima format gabungan juga, dan anak tangga
    terakhir `b`/`b*` memastikan selalu ada fallback.
    """
    try:
        limit = int(height)
    except (TypeError, ValueError):
        limit = 720
    limit = max(144, min(limit, 2160))
    return [
        f"bv*[height<={limit}]+ba/b[height<={limit}]/b",
        "bv*+ba/b",
        "b",
        "b*",
    ]


# Variasi player client YouTube. Satu client bisa mengembalikan daftar format
# yang sangat terbatas (contoh: hanya storyboard / hanya SABR) tergantung IP dan
# status cookies; mencoba beberapa client membuat unduhan jauh lebih tahan.
CLIENT_LADDER: list[Optional[list[str]]] = [
    None,  # default yt-dlp
    ["web"],
    ["web_safari"],
    ["android", "ios"],
    ["tv_embedded", "web"],
    ["mweb"],
]


def _ytdlp_version() -> str:
    try:
        import yt_dlp

        return str(getattr(getattr(yt_dlp, "version", None), "__version__", "unknown"))
    except Exception:  # pragma: no cover - yt-dlp selalu terpasang di worker
        return "unknown"


BOT_CHECK_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "confirm you’re not a bot",
    "confirm you're not a bot",
    "cookies",
)


def looks_like_bot_check(message: str) -> bool:
    """True bila YouTube minta verifikasi login (bukan masalah format)."""
    lowered = (message or "").lower()
    return any(marker in lowered for marker in BOT_CHECK_MARKERS)


def _proxy_pool_from_env() -> list[str]:
    """Daftar proxy aktif (hasil filter di dashboard) untuk rotasi."""
    raw = (os.environ.get("YTDLP_PROXY_POOL") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                urls = [str(u) for u in data if isinstance(u, str) and "://" in u]
                if urls:
                    return urls[:10]
        except Exception:
            pass
    single = (settings.YTDLP_PROXY or "").strip()
    return [single] if single else []


def ytdlp_version() -> str:
    """Versi yt-dlp (dipakai pipeline untuk log diagnostik)."""
    return _ytdlp_version()



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
        """Tentukan file cookies yang dipakai yt-dlp (lihat docstring modul).

        Catatan: path eksplisit SELALU dihormati pada setiap pemanggilan. Bila
        path diberikan tetapi file tidak ada, ini error nyata (bukan alasan
        untuk diam-diam download tanpa cookies) — supaya log admin tidak lagi
        menampilkan `cookies=no` tanpa penjelasan.
        """
        if cookies_path:
            if os.path.exists(cookies_path):
                return cookies_path
            raise DownloadError(
                f"cookies_path diberikan tetapi file tidak ditemukan: {cookies_path}",
                category=CATEGORY_COOKIES_MISSING,
            )

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
        require_audio: bool = False,
        require_cookies: bool = False,
    ) -> str:
        """
        Unduh video dengan beberapa lapis fallback.

        Lapisan yang dicoba (berhenti di percobaan pertama yang menghasilkan file):
          1. format ladder  : bv*[height<=H]+ba / b[height<=H] / b / b*
          2. client ladder  : default -> web -> android,ios -> tv_embedded,web
          3. tanpa cookies  : percobaan terakhir bila cookies diduga bermasalah

        Bila semuanya gagal, daftar format yang tersedia ditulis ke log (ikut
        terunggah ke bundle log worker) dan ringkasannya dimasukkan ke pesan
        error supaya admin bisa langsung tahu penyebabnya.
        """
        output_path = str(self.download_dir / output_filename)
        base_opts = self._base_ydl_opts(cookies_path)
        height = int(str(quality).strip()) if str(quality).strip().isdigit() else 720

        pool = _proxy_pool_from_env()
        cookie_available = bool(base_opts.get("cookiefile"))
        cookie_file = str(base_opts.get("cookiefile") or "")
        cookie_id = Path(cookie_file).stem if cookie_file else None
        if cookie_id:
            try:
                cookie_bytes = os.path.getsize(cookie_file)
                cookie_lines = sum(
                    1 for _ in open(cookie_file, "r", encoding="utf-8", errors="replace")
                )
            except OSError:
                cookie_bytes, cookie_lines = 0, 0
            logger.info(
                "cookies yt-dlp aktif: id=%s ukuran=%sB baris=%s",
                cookie_id,
                cookie_bytes,
                cookie_lines,
            )
        else:
            logger.warning(
                "cookies yt-dlp TIDAK tersedia untuk %s (pool kosong / tidak diteruskan).",
                url[:120],
            )
        if require_cookies and not cookie_available:
            raise DownloadError(
                "Cookies wajib untuk YouTube tetapi tidak tersedia/diteruskan ke yt-dlp.",
                category=CATEGORY_COOKIES_MISSING,
                cookie_id=cookie_id,
                ytdlp_version=_ytdlp_version(),
            )
        if require_audio:
            # Hanya format yang menjamin audio (video + audio-only).
            formats = [
                f"bv*[height<={height}]+ba",
                "bv*+ba",
                "ba+bv*",
            ]
        else:
            formats = format_ladder(height)

        # (clients, format, pakai_cookie, proxy)
        attempts: list[tuple[Optional[list[str]], str, bool, Optional[str]]] = []

        # L1: cookies (+ PO token otomatis dari plugin bgutil bila aktif).
        for clients in CLIENT_LADDER:
            for fmt in formats:
                attempts.append((clients, fmt, cookie_available, None))

        # L2: tanpa cookies (cookie rusak / tidak diperlukan).
        for fmt in formats[:2]:
            attempts.append((None, fmt, False, None))

        # L3/L4: proxy dari pool aktif (maks 3 proxy pertama, format utama).
        for proxy_url in pool[:3]:
            attempts.append((None, formats[0], cookie_available, proxy_url))
            attempts.append((["web"], formats[1], cookie_available, proxy_url))

        if not require_audio:
            # Last resort tanpa cookie & tanpa proxy.
            attempts.append((None, "b", False, None))

        loop = asyncio.get_event_loop()
        errors: list[str] = []
        attempts_meta: list[dict[str, Any]] = []

        for clients, fmt, use_cookies, proxy_url in attempts:
            ydl_opts: Dict[str, Any] = dict(base_opts)
            if not use_cookies:
                ydl_opts.pop("cookiefile", None)
            # Proxy hanya dipakai pada lapis proxy; lapis awal tetap langsung.
            ydl_opts.pop("proxy", None)
            if proxy_url:
                ydl_opts["proxy"] = proxy_url

            ydl_opts.update(
                {
                    "format": fmt,
                    "merge_output_format": "mp4",
                    "format_sort": [
                        "ext:mp4:m4a",
                        "vcodec:h264",
                        "acodec:aac",
                        f"res:{height}",
                    ],
                    # WAJIB %(ext)s: URL file langsung (R2/CDN) disimpan tanpa
                    # ekstensi sehingga ffprobe berikutnya gagal.
                    "outtmpl": f"{output_path}.%(ext)s",
                    "retries": 2,
                    "fragment_retries": 2,
                }
            )

            extractor_args = {
                key: dict(value) for key, value in (base_opts.get("extractor_args") or {}).items()
            }
            if clients:
                youtube_args = extractor_args.setdefault("youtube", {})
                youtube_args["player_client"] = list(clients)
            if extractor_args:
                ydl_opts["extractor_args"] = extractor_args

            has_cookie = bool(ydl_opts.get("cookiefile"))
            proxy_tag = ("proxy=" + proxy_url.split("@")[-1]) if proxy_url else "direct"
            label = (
                f"format={fmt} clients={','.join(clients) if clients else 'default'} "
                f"cookies={'yes' if has_cookie else 'no'} {proxy_tag}"
            )

            try:
                await loop.run_in_executor(None, self._download, url, ydl_opts)
            except Exception as exc:  # yt_dlp.utils.DownloadError atau jaringan
                first_line = (str(exc).splitlines() or [""])[0][:180]
                errors.append(f"{label} -> {type(exc).__name__}: {first_line}")
                attempts_meta.append(
                    {
                        "label": label,
                        "format": fmt,
                        "clients": list(clients) if clients else [],
                        "cookies": has_cookie,
                        "proxy": bool(proxy_url),
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:4000],
                        "category": classify_download_error(str(exc)),
                    }
                )
                logger.warning("unduhan gagal [%s]: %s", label, first_line)
                self._cleanup_partial(output_path)
                continue

            found = self._locate_download(output_path)
            if found:
                logger.info("unduhan berhasil [%s] -> %s", label, found)
                return found

            errors.append(f"{label} -> tidak ada file hasil unduhan")
            self._cleanup_partial(output_path)

        formats = self._describe_formats(url, base_opts)
        attempts_text = " || ".join(errors[-6:])
        hint = ""
        if looks_like_bot_check(attempts_text):
            # Kasus paling umum di Vast/VPS: IP datacenter diminta login.
            hint = (
                " | HINT: YouTube meminta verifikasi login (bot check). "
                "Unggah cookies YouTube di Settings > YouTube Cookies, lalu ulangi task. "
            )
        category = classify_download_error(attempts_text)
        message = (
            "yt-dlp gagal mengunduh setelah semua format/client dicoba | "
            f"yt-dlp={_ytdlp_version()} | formats_tersedia={formats}"
            + hint
            + " || "
            + attempts_text
        )
        raise DownloadError(
            message,
            category=category,
            attempts=attempts_meta,
            ytdlp_version=_ytdlp_version(),
            cookie_id=cookie_id,
            cookie_used=cookie_available,
            http_status=http_status_from(attempts_text),
        )

    def _cleanup_partial(self, output_path: str) -> None:
        """Hapus sisa unduhan gagal agar percobaan berikutnya tidak bercampur."""
        folder = Path(output_path).parent
        stem = Path(output_path).name
        try:
            for entry in folder.glob(f"{stem}*"):
                try:
                    entry.unlink()
                except OSError:
                    continue
        except OSError:
            return

    def _locate_download(self, output_path: str) -> Optional[str]:
        """Cari file hasil unduhan (dengan ekstensi, atau tanpa ekstensi)."""
        folder = Path(output_path).parent
        stem = Path(output_path).name
        candidates = [Path(f"{output_path}.{ext}") for ext in ("mp4", "mkv", "webm")]
        candidates.append(Path(output_path))
        # yt-dlp juga bisa menyimpan gabungan dengan nama <stem>.f137.mp4
        candidates.extend(sorted(folder.glob(f"{stem}.f*.mp4")))

        for path in candidates:
            if not path.exists() or path.stat().st_size <= 0:
                continue
            if not path.suffix:
                renamed = Path(f"{path}.mp4")
                try:
                    os.replace(path, renamed)
                    return str(renamed)
                except OSError:
                    return str(path)
            return str(path)
        return None

    def _describe_formats(self, url: str, ydl_opts: dict) -> str:
        """Ringkas daftar format yang tersedia (untuk pesan error + log)."""
        import yt_dlp

        opts = {key: value for key, value in ydl_opts.items() if key != "cookiefile"}
        opts = dict(opts)
        opts.update({"quiet": True, "no_warnings": True, "skip_download": True})
        opts.pop("format", None)
        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(url, download=False) or {}
        except Exception as exc:
            logger.warning("gagal membaca daftar format: %s", str(exc)[:200])
            return f"tidak bisa dibaca ({type(exc).__name__})"

        formats = info.get("formats") or []
        if not formats:
            return "kosong (0 format)"

        rows = []
        for fmt in formats:
            rows.append(
                f"{fmt.get('format_id')} ext={fmt.get('ext')} h={fmt.get('height')} "
                f"v={fmt.get('vcodec')} a={fmt.get('acodec')}"
            )
        logger.warning("format tersedia (%s): %s", len(rows), " | ".join(rows[:40]))
        ids = ",".join(str(fmt.get("format_id")) for fmt in formats[:12])
        return f"{len(rows)} format [ids: {ids}]"
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

