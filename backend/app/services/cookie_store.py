"""
Cookie store & rotasi otomatis untuk yt-dlp.

Kenapa rotasi otomatis mungkin?
  yt-dlp menyimpan BALIK cookie jar ke `cookiefile` saat `YoutubeDL.close()`
  (yt_dlp/YoutubeDL.py -> save_cookies()). Jadi token jangka pendek yang
  di-refresh YouTube (mis. __Secure-1PSIDTS) ikut ter-update di file cache.
  `sync_back()` membaca file itu lalu mengenkripsinya ulang ke database.

Yang TIDAK bisa diotomatiskan sepenuhnya: bila sesi Google benar-benar
dicabut/kedaluwarsa, cookies baru harus diekspor manual lewat endpoint admin.
"""
import asyncio
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_field, encrypt_field
from app.models.ytdlp_cookie import (
    COOKIE_STATUS_ACTIVE,
    COOKIE_STATUS_DISABLED,
    COOKIE_STATUS_EXPIRED,
    YtdlpCookie,
)

logger = logging.getLogger(__name__)

settings = get_settings()

# Pesan error yt-dlp yang menandakan cookies benar-benar tidak berlaku lagi.
COOKIE_INVALID_MARKERS = (
    "cookies are no longer valid",
    "login required",
    "please sign in",
    "account has been terminated",
)

# Bot-check BUKAN bukti cookies invalid: bisa karena IP datacenter.
BOT_CHECK_MARKERS = (
    "sign in to confirm",
    "confirm you're not a bot",
    "not a bot",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cache_dir() -> Path:
    path = Path(settings.YTDLP_COOKIE_CACHE_DIR or "./.cache/ytdlp_cookies")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cache_path(cookie_id: UUID) -> Path:
    return _cache_dir() / f"{cookie_id}.txt"


def looks_expired(error_text: Optional[str]) -> bool:
    """True bila pesan error menandakan cookies perlu diganti.

    Sengaja TIDAK memakai teks bot-check: IP datacenter sering diminta login
    walau cookies masih valid. Menandai expired di kasus itu membuat pool
    kosong dan semua task berikutnya berjalan tanpa cookies.
    """
    if not error_text:
        return False
    lowered = error_text.lower()
    return any(marker in lowered for marker in COOKIE_INVALID_MARKERS)


def looks_like_bot_check(error_text: Optional[str]) -> bool:
    lowered = (error_text or "").lower()
    return any(marker in lowered for marker in BOT_CHECK_MARKERS)


def validate_cookies_text(text: str) -> None:
    """Pastikan isi benar-benar cookies.txt Netscape + lengkap untuk login.

    Banyak ekspor "hanya cookie yang terlihat" menyertakan __Secure-3PSID saja.
    Cookie seperti itu membuat yt-dlp mengira sudah login (bot-check hilang)
    tetapi YouTube hanya memberi storyboard (tanpa format video). Validasi ini
    menolak ekspor tidak lengkap lebih awal dengan pesan yang jelas.
    """
    if not text.strip():
        raise ValueError("Isi cookies kosong.")
    if "Netscape HTTP Cookie File" not in text and "\t" not in text:
        raise ValueError(
            "Isi cookies tidak terlihat seperti cookies.txt format Netscape. "
            "Ekspor ulang dengan ekstensi 'Get cookies.txt LOCALLY'."
        )
    if "youtube.com" not in text:
        raise ValueError("Cookies tidak berisi domain youtube.com.")

    names: set[str] = set()
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 6 and "youtube" in parts[0].lower():
            names.add(parts[5])

    # Minimal satu cookie auth utama harus ada. Tanpa ini, sesi tidak lengkap.
    required_any = {"SID", "__Secure-1PSID", "SAPISID", "__Secure-1PAPISID"}
    if names and not (names & required_any):
        raise ValueError(
            "Cookie YouTube tidak lengkap (hanya cookie __Secure-3PSID*). "
            "Ekspor ulang cookies youtube.com dari browser yang benar-benar login "
            "dan pastikan SID/HSID/SSID/APISID/SAPISID ikut tersimpan."
        )


async def add_cookie(db: AsyncSession, label: str, cookies_text: str) -> YtdlpCookie:
    """Simpan cookies baru (terenkripsi). Menimpa label yang sama."""
    validate_cookies_text(cookies_text)

    existing = (
        await db.execute(select(YtdlpCookie).where(YtdlpCookie.label == label))
    ).scalar_one_or_none()

    if existing:
        existing.encrypted_cookies = encrypt_field(cookies_text)
        existing.status = COOKIE_STATUS_ACTIVE
        existing.fail_count = 0
        existing.last_error = None
        existing.refreshed_by_ytdlp = False
        _cache_path(existing.id).unlink(missing_ok=True)
        await db.commit()
        await db.refresh(existing)
        return existing

    cookie = YtdlpCookie(
        label=label,
        encrypted_cookies=encrypt_field(cookies_text),
        status=COOKIE_STATUS_ACTIVE,
    )
    db.add(cookie)
    await db.commit()
    await db.refresh(cookie)
    return cookie


async def list_cookies(db: AsyncSession) -> Sequence[YtdlpCookie]:
    result = await db.execute(select(YtdlpCookie).order_by(YtdlpCookie.created_at))
    return result.scalars().all()


async def delete_cookie(db: AsyncSession, cookie_id: UUID) -> bool:
    cookie = await db.get(YtdlpCookie, cookie_id)
    if not cookie:
        return False
    _cache_path(cookie.id).unlink(missing_ok=True)
    await db.delete(cookie)
    await db.commit()
    return True


def pick_cookie(candidates: Sequence[YtdlpCookie]) -> Optional[YtdlpCookie]:
    """Pilih cookies aktif secara acak supaya beban merata antar akun.

    Dipisah dari `acquire()` agar mudah dites tanpa database. Kandidat yang
    masuk ke sini WAJIB sudah difilter `status == active`.
    """
    items = list(candidates)
    return random.choice(items) if items else None


async def acquire(
    db: AsyncSession, dest_dir: Optional[Path] = None
) -> Optional[tuple[YtdlpCookie, str]]:
    """Ambil cookies aktif secara ACAK (bukan selalu satu akun yang sama).

    Semua cookies `active` menjadi kandidat. Pemilihan acak membuat beberapa
    akun terpakai bergantian; `last_used_at` tetap diperbarui untuk monitoring.
    File cache ditulis 0600 dan writable agar yt-dlp bisa menulis balik token
    yang sudah dirotasi. Bila `dest_dir` diberikan, cookies DISALIN ke folder
    task (file unik per task) supaya dua task paralel tidak berebut file yang
    sama saat yt-dlp menulis balik cookie jar.
    """
    result = await db.execute(
        select(YtdlpCookie).where(YtdlpCookie.status == COOKIE_STATUS_ACTIVE)
    )
    cookie = pick_cookie(result.scalars().all())
    if not cookie:
        return None

    try:
        plaintext = decrypt_field(cookie.encrypted_cookies)
    except Exception as exc:  # ENCRYPTION_KEY berubah / data korup
        logger.error("Gagal mendekripsi cookies '%s': %s", cookie.label, exc)
        cookie.status = COOKIE_STATUS_EXPIRED
        cookie.last_error = f"dekripsi gagal: {exc}"
        await db.commit()
        return None

    path = _cache_path(cookie.id)
    path.write_text(plaintext, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # Windows tidak mendukung chmod penuh
        pass

    task_path = path
    if dest_dir is not None:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            task_path = dest_dir / f"cookies_{cookie.id}.txt"
            task_path.write_text(plaintext, encoding="utf-8")
            try:
                task_path.chmod(0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.warning("Gagal menyalin cookies ke folder task: %s", exc)
            task_path = path

    cookie.last_used_at = _now()
    await db.commit()
    await db.refresh(cookie)
    return cookie, str(task_path)


async def sync_back(
    db: AsyncSession, cookie: YtdlpCookie, cookie_path: Optional[str] = None
) -> bool:
    """Simpan balik isi cache -> DB bila yt-dlp sudah merotasi token.

    `cookie_path` = file yang benar-benar dipakai yt-dlp (salinan per-task).
    Return True bila ada perubahan yang tersimpan.
    """
    path = Path(cookie_path) if cookie_path else _cache_path(cookie.id)
    if not path.exists():
        return False

    current = path.read_text(encoding="utf-8", errors="replace")
    if not current.strip():
        return False

    try:
        stored = decrypt_field(cookie.encrypted_cookies)
    except Exception:
        stored = None

    if current == stored:
        return False

    cookie.encrypted_cookies = encrypt_field(current)
    cookie.refreshed_by_ytdlp = True
    await db.commit()
    logger.info("Cookies '%s' dirotasi oleh yt-dlp dan disimpan balik.", cookie.label)
    return True


async def report_success(db: AsyncSession, cookie: YtdlpCookie) -> None:
    cookie.fail_count = 0
    cookie.success_count = cookie.success_count + 1
    cookie.last_checked_at = _now()
    cookie.last_error = None
    if cookie.status != COOKIE_STATUS_ACTIVE:
        cookie.status = COOKIE_STATUS_ACTIVE
    await db.commit()


async def report_failure(
    db: AsyncSession, cookie: YtdlpCookie, error_text: Optional[str]
) -> bool:
    """Catat kegagalan. Return True bila cookies ditandai expired."""
    cookie.fail_count = cookie.fail_count + 1
    cookie.last_checked_at = _now()
    cookie.last_error = (error_text or "")[:2000]

    bot_check = looks_like_bot_check(error_text)
    expired = looks_expired(error_text) or (
        not bot_check and cookie.fail_count >= settings.YTDLP_COOKIE_MAX_FAILURES
    )
    if expired:
        cookie.status = COOKIE_STATUS_EXPIRED
        logger.warning(
            "Cookies '%s' ditandai EXPIRED (fail_count=%s, bot_check=%s): %s",
            cookie.label,
            cookie.fail_count,
            bot_check,
            (error_text or "")[:200],
        )
    elif bot_check:
        logger.warning(
            "Cookies '%s' gagal karena bot-check IP (bukan cookies invalid): %s",
            cookie.label,
            (error_text or "")[:200],
        )
    await db.commit()
    return expired


async def mark_disabled(db: AsyncSession, cookie: YtdlpCookie) -> None:
    cookie.status = COOKIE_STATUS_DISABLED
    await db.commit()


async def reactivate(db: AsyncSession, cookie: YtdlpCookie) -> None:
    cookie.status = COOKIE_STATUS_ACTIVE
    cookie.fail_count = 0
    cookie.last_error = None
    await db.commit()



# ---------------------------------------------------------------------------
# Probe (uji apakah cookies masih valid) - inti rotasi otomatis
# ---------------------------------------------------------------------------
def _probe_sync(cookiefile: str, url: str) -> tuple[bool, Optional[str]]:
    import yt_dlp

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "cookiefile": cookiefile,
        "extract_flat": True,
        "socket_timeout": 20,
    }
    if settings.YTDLP_PROXY:
        opts["proxy"] = settings.YTDLP_PROXY

    try:
        # yt-dlp mengetik params sebagai TypedDict `_Params`; cast agar dict
        # dinamis ini tidak dianggap salah tipe.
        with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
            ydl.extract_info(url, download=False)
        return True, None
    except Exception as exc:  # DownloadError dan turunannya
        return False, str(exc)


async def probe(db: AsyncSession, cookie: YtdlpCookie) -> tuple[bool, Optional[str]]:
    """Uji cookies dengan satu video probe, lalu update statusnya."""
    path = _cache_path(cookie.id)
    if not path.exists():
        path.write_text(decrypt_field(cookie.encrypted_cookies), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    loop = asyncio.get_event_loop()
    ok, error = await loop.run_in_executor(
        None, _probe_sync, str(path), settings.YTDLP_COOKIE_PROBE_URL
    )

    # yt-dlp mungkin sudah merotasi token selama probe
    await sync_back(db, cookie)

    if ok:
        await report_success(db, cookie)
    else:
        await report_failure(db, cookie, error)
    return ok, error


async def probe_all(db: AsyncSession) -> list[dict]:
    """Probe semua cookies aktif. Dipakai cron / endpoint admin."""
    results: list[dict] = []
    for cookie in await list_cookies(db):
        if cookie.status != COOKIE_STATUS_ACTIVE:
            continue
        ok, error = await probe(db, cookie)
        results.append(
            {
                "id": str(cookie.id),
                "label": cookie.label,
                "ok": ok,
                "error": error,
                "status": cookie.status,
            }
        )
    return results



@asynccontextmanager
async def cookie_session(db: AsyncSession):
    """Context manager untuk pipeline download.

    Contoh pemakaian di worker:

        async with cookie_session(db) as (cookie, cookiefile):
            path = await downloader.download_video(url, name, cookies_path=cookiefile)
            await report_success(db, cookie)      # atau report_failure(...)

    Saat keluar dari blok, isi cache ditulis balik ke DB sehingga token hasil
    rotasi yt-dlp tidak hilang.
    """
    acquired = await acquire(db)
    cookie, cookiefile = acquired if acquired else (None, None)
    try:
        yield cookie, cookiefile
    finally:
        if cookie is not None:
            try:
                await sync_back(db, cookie)
            except Exception as exc:  # jangan gagalkan job karena sync gagal
                logger.warning("sync_back cookies '%s' gagal: %s", cookie.label, exc)

