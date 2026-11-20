"""Hidrasi kredensial database ke `settings` runtime.

Cookies YouTube, token Hugging Face, dan kredensial storage TIDAK berada di
env proses: admin menyimpannya terenkripsi di database (`platform_settings`,
pool `ytdlp_cookies`, registry storage). Tanpa hidrasi ulang setiap start,
`settings` kosong setelah container restart sehingga:

  - tab admin *Instance -> Environment* menampilkan \"kosong\" walau sudah diisi;
  - instance worker dibuat TANPA cookies / HF token (download rawan bot-check).

Sumber nilai = sumber yang sama dengan dashboard, jadi tampilan admin dan env
dispatch selalu konsisten.
"""
import base64
import logging
from typing import Any, Dict, Tuple

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decrypt_field
from app.db.session import AsyncSessionLocal
from app.models.ytdlp_cookie import COOKIE_STATUS_ACTIVE, YtdlpCookie

logger = logging.getLogger(__name__)
settings = get_settings()

YOUTUBE_KEY = "youtube"


def encode_cookies_base64(plain: str) -> str:
    """base64 dari isi cookies.txt (format yang dibaca downloader & worker)."""
    return base64.b64encode((plain or "").encode("utf-8")).decode("ascii")


async def _read_youtube_base64() -> Tuple[str, str]:
    """(base64, sumber) cookies aktif: platform_settings lalu pool DB."""
    from app.services import platform_settings as ps

    async with AsyncSessionLocal() as db:
        stored = await ps.get_setting(db, YOUTUBE_KEY, {}) or {}
        encoded = stored.get("cookies_base64_enc") if isinstance(stored, dict) else None
        if encoded:
            try:
                return decrypt_field(str(encoded)), "platform_settings"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gagal dekripsi cookies global YouTube: %s", exc)
        row = (
            await db.execute(
                select(YtdlpCookie)
                .where(YtdlpCookie.status == COOKIE_STATUS_ACTIVE)
                .order_by(YtdlpCookie.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return "", ""
        try:
            return encode_cookies_base64(decrypt_field(row.encrypted_cookies)), "pool"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gagal dekripsi cookies '%s': %s", row.label, exc)
            return "", ""


async def _read_hf_token() -> str:
    from app.services import model_sources

    async with AsyncSessionLocal() as db:
        try:
            _provider, values = await model_sources.resolved_values(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gagal membaca kredensial sumber model: %s", exc)
            return ""
        return str(values.get("hf_token") or "").strip()


def _apply_storage(config: Dict[str, Any]) -> Dict[str, Any]:
    """Kredensial storage primary (R2/S3/B2) -> env worker."""
    items = config.get("items") if isinstance(config, dict) else None
    items = items if isinstance(items, list) else []
    primary = next(
        (
            row
            for row in items
            if isinstance(row, dict) and row.get("id") == config.get("primary_id")
        ),
        None,
    )
    if primary is None:
        return {"storage_set": False}
    try:
        access = decrypt_field(primary["access_key_enc"]) if primary.get("access_key_enc") else ""
        secret = decrypt_field(primary["secret_key_enc"]) if primary.get("secret_key_enc") else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal dekripsi kredensial storage: %s", exc)
        return {"storage_set": False}
    if access:
        settings.R2_ACCESS_KEY_ID = access
    if secret:
        settings.R2_SECRET_ACCESS_KEY = secret
    if primary.get("endpoint"):
        settings.R2_ENDPOINT_URL = str(primary["endpoint"])
    if primary.get("bucket"):
        settings.R2_BUCKET_NAME = str(primary["bucket"])
    settings.R2_PUBLIC_DOMAIN = str(primary.get("public_domain") or "")
    return {
        "storage_set": bool(access and secret),
        "storage_provider": primary.get("provider"),
    }


async def hydrate_youtube_cookies() -> Dict[str, Any]:
    """Isi `settings.YTDLP_COOKIES_BASE64` dari database (kalau ada)."""
    encoded, source = await _read_youtube_base64()
    if encoded:
        settings.YTDLP_COOKIES_BASE64 = encoded
    return {
        "cookies_set": bool(encoded),
        "cookies_source": source or None,
        "cookies_chars": len(encoded),
    }


async def read_active_cookies_text() -> Tuple[str, str]:
    """cookies.txt (plaintext) aktif + sumbernya.

    Dipakai endpoint internal yang diambil worker saat boot, supaya cookies
    tidak perlu dikirim lewat env Vast (batas env ±4 KB, dan metadata instance
    Vast bisa dibaca dari dashboard). Sumbernya sama dengan dashboard admin:
    `platform_settings` lebih dulu, lalu pool tabel `ytdlp_cookies`.
    """
    encoded, source = await _read_youtube_base64()
    if not encoded:
        return "", ""
    try:
        plain = base64.b64decode(
            encoded.encode("ascii"), validate=False
        ).decode("utf-8", "ignore")
        return plain, source
    except Exception as exc:  # noqa: BLE001 - cookies korup bukan alasan 500
        logger.warning("Cookies aktif tidak bisa didekode: %s", exc)
        return "", ""


async def hydrate_hf_token() -> Dict[str, Any]:
    """Isi `settings.HF_TOKEN` dari setelan sumber model Whisper."""
    token = await _read_hf_token()
    if token:
        settings.HF_TOKEN = token
    return {"hf_token_set": bool(token)}


async def hydrate_runtime_credentials() -> Dict[str, Any]:
    """Muat cookies YouTube, HF token, dan storage primary dari database."""
    summary: Dict[str, Any] = {}
    for name, loader in (
        ("youtube", hydrate_youtube_cookies),
        ("huggingface", hydrate_hf_token),
    ):
        try:
            summary[name] = await loader()
        except Exception as exc:  # noqa: BLE001 - jangan gagalkan startup
            logger.warning("Hidrasi kredensial %s gagal: %s", name, exc)
            summary[name] = {"error": str(exc)[:200]}
    try:
        from app.services import storage_registry as sr

        summary["storage"] = _apply_storage(sr.get_config())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hidrasi kredensial storage gagal: %s", exc)
        summary["storage"] = {"error": str(exc)[:200]}
    return summary
