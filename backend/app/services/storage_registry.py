"""
Registry penyimpanan objek multi-provider (R2, B2, S3, dll).

Semua provider yang didukung berbicara protokol S3, jadi satu engine cukup.
Kredensial disimpan terenkripsi (AES-256-GCM) di `platform_settings` key
`storage`, dan konfigurasi di-cache di memori supaya pipeline bisa memanggil
`get_storage()` secara sinkron (tanpa await DB di jalur render klip).

Migrasi aman: bila belum ada konfigurasi, dibuat otomatis dari env R2_* yang
sudah dipakai selama ini, sehingga deployment lama tidak berubah perilaku.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.security import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

STORAGE_KEY = "storage"

# Preset provider: endpoint + region default + catatan path-style.
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "r2": {
        "label": "Cloudflare R2",
        "endpoint": "https://<account_id>.r2.cloudflarestorage.com",
        "region": "auto",
        "path_style": False,
        "hint": "Public domain wajib diisi agar URL klip bisa dibuka publik.",
    },
    "b2": {
        "label": "Backblaze B2 (S3 API)",
        "endpoint": "https://s3.<region>.backblazeb2.com",
        "region": "us-west-004",
        "path_style": False,
        "hint": "Gunakan application key S3 (bukan master key) + bucket unik.",
    },
    "s3": {
        "label": "AWS S3",
        "endpoint": "https://s3.<region>.amazonaws.com",
        "region": "ap-southeast-1",
        "path_style": False,
        "hint": "Bisa juga memakai endpoint regional otomatis (kosongkan endpoint).",
    },
    "wasabi": {
        "label": "Wasabi",
        "endpoint": "https://s3.<region>.wasabisys.com",
        "region": "ap-northeast-1",
        "path_style": False,
        "hint": "Region ditentukan saat membuat bucket.",
    },
    "spaces": {
        "label": "DigitalOcean Spaces",
        "endpoint": "https://<region>.digitaloceanspaces.com",
        "region": "sgp1",
        "path_style": False,
        "hint": "Aktifkan CDN bila ingin URL publik cepat.",
    },
    "linode": {
        "label": "Linode/Akamai Object Storage",
        "endpoint": "https://<region>.linodeobjects.com",
        "region": "sg-sin-1",
        "path_style": False,
        "hint": "Set bucket ACL public-read bila domain publik dipakai.",
    },
    "scaleway": {
        "label": "Scaleway Object Storage",
        "endpoint": "https://s3.<region>.scw.cloud",
        "region": "fr-par",
        "path_style": False,
        "hint": "Buat API key dengan izin Object Storage full access.",
    },
    "hetzner": {
        "label": "Hetzner Object Storage",
        "endpoint": "https://<region>.your-objectstorage.com",
        "region": "nbg1",
        "path_style": True,
        "hint": "Path-style dipakai Hetzner.",
    },
    "supabase": {
        "label": "Supabase Storage (S3)",
        "endpoint": "https://<project-ref>.supabase.co/storage/v1/s3",
        "region": "ap-northeast-1",
        "path_style": True,
        "hint": "Gunakan access key dari menu Storage > S3 access keys.",
    },
    "gcs": {
        "label": "Google Cloud Storage (S3 interop)",
        "endpoint": "https://storage.googleapis.com",
        "region": "auto",
        "path_style": True,
        "hint": "Aktifkan interoperability key (HMAC) di GCS.",
    },
    "idrive": {
        "label": "IDrive e2",
        "endpoint": "https://<region>.idrivee2-<n>.com",
        "region": "us-east-1",
        "path_style": False,
        "hint": "Endpoint lengkap tercantum di dashboard IDrive.",
    },
    "storj": {
        "label": "Storj (S3 gateway)",
        "endpoint": "https://gateway.storjshare.io",
        "region": "global",
        "path_style": False,
        "hint": "Buat access grant dengan izin baca/tulis.",
    },
    "filebase": {
        "label": "Filebase (IPFS/S3)",
        "endpoint": "https://s3.filebase.com",
        "region": "us-east-1",
        "path_style": False,
        "hint": "Isi public domain bila memakai gateway publik.",
    },
    "minio": {
        "label": "MinIO / S3 kompatibel",
        "endpoint": "https://s3.domain-anda.com",
        "region": "us-east-1",
        "path_style": True,
        "hint": "Endpoint manual; biasanya path-style + TLS self-signed.",
    },
}

DEFAULT_STORAGE: Dict[str, Any] = {"primary_id": None, "mirror_ids": [], "items": []}

_lock = threading.Lock()
_config: Dict[str, Any] = dict(DEFAULT_STORAGE)


def mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value)
    if len(text) <= 6:
        return "***"
    return text[:3] + "***" + text[-3:]


def normalize_item(raw: dict) -> Dict[str, Any]:
    provider = str(raw.get("provider") or "r2").lower()
    preset = PROVIDERS.get(provider, PROVIDERS["minio"])
    return {
        "id": str(raw.get("id") or ""),
        "name": str(raw.get("name") or preset["label"])[:60],
        "provider": provider if provider in PROVIDERS else "minio",
        "bucket": str(raw.get("bucket") or "").strip(),
        "endpoint": str(raw.get("endpoint") or preset["endpoint"]).strip(),
        "region": str(raw.get("region") or preset["region"]).strip(),
        "path_style": bool(raw.get("path_style", preset["path_style"])),
        "public_domain": str(raw.get("public_domain") or "").strip().rstrip("/"),
        "path_prefix": str(raw.get("path_prefix") or "").strip().strip("/"),
        "access_key_enc": raw.get("access_key_enc") or "",
        "secret_key_enc": raw.get("secret_key_enc") or "",
        "enabled": bool(raw.get("enabled", True)),
        "last_check": raw.get("last_check") or None,
    }


def normalize_config(raw: Optional[dict]) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    items = [normalize_item(item) for item in (raw.get("items") or []) if isinstance(item, dict)]
    ids = [item["id"] for item in items]
    primary = raw.get("primary_id")
    if primary not in ids:
        primary = ids[0] if ids else None
    mirrors = [mid for mid in (raw.get("mirror_ids") or []) if mid in ids and mid != primary]
    return {"primary_id": primary, "mirror_ids": mirrors, "items": items}


def _from_env() -> Dict[str, Any]:
    settings = get_settings()
    if not (settings.R2_ENDPOINT_URL and settings.R2_BUCKET_NAME):
        return dict(DEFAULT_STORAGE)
    item = normalize_item(
        {
            "id": "env-r2",
            "name": "R2 (env)",
            "provider": "r2",
            "bucket": settings.R2_BUCKET_NAME,
            "endpoint": settings.R2_ENDPOINT_URL,
            "region": "auto",
            "public_domain": settings.R2_PUBLIC_DOMAIN or "",
            "access_key_enc": encrypt_field(settings.R2_ACCESS_KEY_ID or ""),
            "secret_key_enc": encrypt_field(settings.R2_SECRET_ACCESS_KEY or ""),
            "enabled": True,
        }
    )
    return {"primary_id": "env-r2", "mirror_ids": [], "items": [item]}


def set_config(config: Dict[str, Any]) -> Dict[str, Any]:
    global _config
    with _lock:
        _config = normalize_config(config)
        return _config


def get_config() -> Dict[str, Any]:
    return _config


@dataclass
class ResolvedStorage:
    item: Dict[str, Any]
    client: Any
    bucket: str
    public_domain: str
    path_prefix: str


def resolve(item: Dict[str, Any], timeout: int = 30) -> ResolvedStorage:
    """Bangun klien boto3 untuk satu item konfigurasi."""
    access_key = decrypt_field(item["access_key_enc"]) if item.get("access_key_enc") else ""
    secret_key = decrypt_field(item["secret_key_enc"]) if item.get("secret_key_enc") else ""
    if not access_key or not secret_key:
        raise ValueError("kredensial storage belum diisi")
    endpoint = (item.get("endpoint") or "").strip()
    region = item.get("region") or "auto"
    # Backblaze: region WAJIB sama dengan region di endpoint (ca-east-006, dsb).
    # Salah region -> SigV4 ditolak dan koneksi kadang ditutup provider.
    if item.get("provider") == "b2" and endpoint:
        match = re.search(r"s3\.([a-z0-9-]+)\.backblazeb2\.com", endpoint)
        if match:
            region = match.group(1)
    client = boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if item.get("path_style") else "virtual"},
            connect_timeout=timeout,
            read_timeout=timeout,
            retries={"max_attempts": 2},
        ),
    )
    return ResolvedStorage(
        item=item,
        client=client,
        bucket=item.get("bucket") or "",
        public_domain=(item.get("public_domain") or "").rstrip("/"),
        path_prefix=(item.get("path_prefix") or "").strip("/"),
    )

class StorageService:
    """API storage tunggal untuk seluruh aplikasi (primary + mirror)."""

    def __init__(self) -> None:
        config = get_config()
        self.items: List[Dict[str, Any]] = config.get("items", [])
        self.primary_id = config.get("primary_id")
        self.mirror_ids: List[str] = config.get("mirror_ids", [])

    # ---------- internal ----------
    def _item(self, item_id: Optional[str]) -> Optional[Dict[str, Any]]:
        for item in self.items:
            if item.get("id") == item_id and item.get("enabled", True):
                return item
        return None

    def _primary_item(self) -> Optional[Dict[str, Any]]:
        item = self._item(self.primary_id)
        if item:
            return item
        for candidate in self.items:
            if candidate.get("enabled", True):
                return candidate
        return None

    def _resolved(self, item: Dict[str, Any]) -> ResolvedStorage:
        return resolve(item)

    def _key(self, resolved: ResolvedStorage, object_key: str) -> str:
        prefix = resolved.path_prefix
        return prefix + "/" + object_key if prefix else object_key

    def _url(self, resolved: ResolvedStorage, object_key: str) -> str:
        key = self._key(resolved, object_key)
        if resolved.public_domain:
            return resolved.public_domain + "/" + key
        try:
            return resolved.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": resolved.bucket, "Key": key},
                ExpiresIn=7 * 24 * 3600,
            )
        except Exception:
            return ""

    def _handle(self):
        item = self._primary_item()
        if not item:
            return None, None
        try:
            return item, self._resolved(item)
        except Exception as exc:
            # Tanpa log ini, kegagalan dekripsi/kredensial tampak seperti
            # "storage belum dikonfigurasi" tanpa petunjuk apa pun.
            logger.warning(
                "Storage '%s' tidak bisa dipakai (%s): %s",
                item.get("id"),
                item.get("provider"),
                exc,
            )
            return None, None

    # ---------- replikasi ke mirror ----------
    def _replicate(self, object_key: str, data: Optional[bytes], local_path: Optional[str], content_type: str) -> None:
        if not self.mirror_ids:
            return

        def worker() -> None:
            for mirror_id in self.mirror_ids:
                item = self._item(mirror_id)
                if not item:
                    continue
                try:
                    resolved = self._resolved(item)
                    key = self._key(resolved, object_key)
                    if local_path:
                        resolved.client.upload_file(
                            local_path,
                            resolved.bucket,
                            key,
                            ExtraArgs={"ContentType": content_type},
                        )
                    elif data is not None:
                        resolved.client.put_object(
                            Bucket=resolved.bucket,
                            Key=key,
                            Body=data,
                            ContentType=content_type,
                            CacheControl="public, max-age=31536000, immutable",
                        )
                except Exception:
                    continue

        threading.Thread(target=worker, daemon=True).start()

    # ---------- API publik (kompatibel R2Storage) ----------
    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: str = "application/octet-stream",
        cache_control: Optional[str] = "public, max-age=31536000, immutable",
    ) -> str:
        item, resolved = self._handle()
        if not resolved:
            raise RuntimeError("storage belum dikonfigurasi (Settings > Storage)")
        extra = {"CacheControl": cache_control} if cache_control else {}
        resolved.client.put_object(
            Bucket=resolved.bucket,
            Key=self._key(resolved, object_key),
            Body=data,
            ContentType=content_type,
            **extra,
        )
        self._replicate(object_key, data, None, content_type)
        return self._url(resolved, object_key)

    def upload_file(
        self,
        local_path: str,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        item, resolved = self._handle()
        if not resolved:
            raise RuntimeError("storage belum dikonfigurasi (Settings > Storage)")
        resolved.client.upload_file(
            local_path,
            resolved.bucket,
            self._key(resolved, object_key),
            ExtraArgs={"ContentType": content_type},
        )
        self._replicate(object_key, None, local_path, content_type)
        return self._url(resolved, object_key)

    def get_public_url(self, object_key: str) -> str:
        item, resolved = self._handle()
        if not resolved:
            return ""
        return self._url(resolved, object_key)

    def delete_file(self, object_key: str) -> bool:
        item, resolved = self._handle()
        if not resolved:
            return False
        try:
            resolved.client.delete_object(Bucket=resolved.bucket, Key=self._key(resolved, object_key))
            return True
        except Exception:
            return False

    def get_presigned_url(self, object_key: str, expiration: int = 3600) -> str:
        item, resolved = self._handle()
        if not resolved:
            return ""
        try:
            return resolved.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": resolved.bucket, "Key": self._key(resolved, object_key)},
                ExpiresIn=expiration,
            )
        except Exception:
            return ""

    def generate_object_key(self, user_id: str, filename: str, folder: str = "outputs") -> str:
        from datetime import datetime, timezone
        from uuid import uuid4

        ext = filename.split(".")[-1] if "." in filename else "mp4"
        unique_id = str(uuid4())[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return folder + "/" + str(user_id) + "/" + timestamp + "_" + unique_id + "." + ext


def get_storage() -> StorageService:
    """Entry point tunggal untuk seluruh aplikasi (sinkron, tanpa DB).

    Konfigurasi dimuat sekali secara lazy. Ini penting untuk **worker** yang
    menjalankan pipeline langsung (bukan lewat startup FastAPI): tanpa lazy load,
    `_config` masih kosong sehingga semua upload gagal dengan pesan
    "storage belum dikonfigurasi (Settings > Storage)" walau dashboard sudah
    berisi provider.
    """
    if not get_config().get("items"):
        _ensure_loaded_sync()
    return StorageService()


def _ensure_loaded_sync() -> None:
    """Muat konfigurasi storage dari DB pada konteks sinkron (worker pipeline).

    Pipeline memanggil `get_storage()` dari dalam event loop async. `asyncio.run()`
    tidak boleh dipakai di sana, jadi konfigurasi dimuat di **thread terpisah**
    yang punya event loop sendiri. Bila tetap gagal (mis. DB tidak terjangkau),
    dipakai seed dari env R2_* supaya upload tidak mati total.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(load_storage_config())
        except Exception as exc:
            logger.warning("Gagal memuat konfigurasi storage dari DB: %s", exc)
    else:
        errors: List[Exception] = []

        def _load() -> None:
            try:
                asyncio.run(load_storage_config())
            except Exception as exc:  # pragma: no cover - jalur thread
                errors.append(exc)

        thread = threading.Thread(target=_load, name="clipzi-storage-load", daemon=True)
        thread.start()
        thread.join(timeout=20)
        if errors:
            logger.warning("Gagal memuat konfigurasi storage dari DB: %s", errors[0])
        elif thread.is_alive():
            logger.warning("Memuat konfigurasi storage melewati batas 20 detik")

    if get_config().get("items"):
        return
    try:
        set_config(_from_env())
    except Exception as exc:
        logger.warning("Seed storage dari env gagal: %s", exc)


async def load_storage_config() -> Dict[str, Any]:
    """Muat konfigurasi dari DB (seed dari env R2 bila belum ada)."""
    from app.db.session import AsyncSessionLocal
    from app.services.platform_settings import get_setting, set_setting

    async with AsyncSessionLocal() as db:
        raw = await get_setting(db, STORAGE_KEY, None)
        if not isinstance(raw, dict) or not raw.get("items"):
            seeded = _from_env()
            await set_setting(db, STORAGE_KEY, seeded)
            return set_config(seeded)
        return set_config(raw)


async def save_storage_config(db, config: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.platform_settings import set_setting

    normalized = normalize_config(config)
    await set_setting(db, STORAGE_KEY, normalized)
    return set_config(normalized)


def public_view(config: Dict[str, Any]) -> Dict[str, Any]:
    """Tampilan aman untuk dashboard (kredensial dimask)."""
    items = []
    for item in config.get("items", []):
        access = ""
        try:
            access = decrypt_field(item["access_key_enc"]) if item.get("access_key_enc") else ""
        except Exception:
            access = ""
        items.append(
            {
                **{k: v for k, v in item.items() if not k.endswith("_enc")},
                "access_key_masked": mask(access),
                "has_credentials": bool(item.get("access_key_enc") and item.get("secret_key_enc")),
            }
        )
    return {
        "primary_id": config.get("primary_id"),
        "mirror_ids": config.get("mirror_ids", []),
        "items": items,
        "providers": [
            {"id": key, **value} for key, value in PROVIDERS.items()
        ],
    }


def credential_warnings(provider: str, access_key: str, secret_key: str) -> List[str]:
    """Peringatan cepat saat format kredensial tidak lazim (menghindari bingung)."""
    warnings: List[str] = []
    key = (access_key or "").strip()
    secret = (secret_key or "").strip()
    if not key or not secret:
        warnings.append("Access key / secret key kosong.")
        return warnings
    if provider == "b2" and len(key) < 20:
        warnings.append(
            "B2: 'Access Key' tampaknya keyID master (pendek). Pakai Application Key -> keyID "
            "(biasanya ±31 karakter) + applicationKey."
        )
    if provider == "r2" and len(key) != 32:
        warnings.append("R2: access key biasanya 32 karakter hex (Access Key ID).")
    if len(secret) < 16:
        warnings.append("Secret key terlalu pendek untuk provider S3 mana pun.")
    return warnings


def _probe(resolved: ResolvedStorage, bucket: str) -> None:
    """put -> head -> delete objek kecil (melempar exception bila gagal)."""
    from uuid import uuid4

    key = "_clipzi_check/" + uuid4().hex + ".txt"
    resolved.client.put_object(
        Bucket=bucket, Key=key, Body=b"clipzi-storage-check", ContentType="text/plain"
    )
    resolved.client.head_object(Bucket=bucket, Key=key)
    resolved.client.delete_object(Bucket=bucket, Key=key)


def _diagnose(item: Dict[str, Any]) -> Dict[str, Any]:
    """Ambil pesan error asli dari provider (beberapa menutup koneksi saat auth gagal)."""
    try:
        resolved = resolve(item, timeout=10)
        resolved.client.list_buckets()
        return {"error_code": None, "error_message": None}
    except ClientError as exc:
        err = exc.response.get("Error", {}) if hasattr(exc, "response") else {}
        return {
            "error_code": err.get("Code"),
            "error_message": err.get("Message"),
        }
    except Exception as exc:
        return {"error_code": type(exc).__name__, "error_message": str(exc)[:200]}


def _hint_for(code: Optional[str], provider: str) -> Optional[str]:
    if not code:
        return None
    if code in ("InvalidAccessKeyId", "Malformed Access Key Id"):
        base = "Access Key tidak valid/ditolak provider."
        if provider == "b2":
            return base + " Backblaze: pakai Application Key -> keyID (±31 karakter), bukan master keyID."
        if provider == "r2":
            return base + " R2: pakai Access Key ID (32 hex) + Secret Access Key (64 hex)."
        return base + " Periksa kembali Access Key ID."
    if code == "SignatureDoesNotMatch":
        return "Secret key salah, atau region tidak cocok dengan endpoint."
    if code == "NoSuchBucket":
        return "Bucket tidak ditemukan di akun/region ini."
    if code in ("AccessDenied", "AllAccessDisabled"):
        return "Key valid tetapi tidak punya izin tulis ke bucket ini."
    if code == "ConnectionClosedError":
        return "Provider menutup koneksi (biasanya karena kredensial salah atau endpoint/region tidak cocok)."
    if code in ("EndpointConnectionError", "ConnectTimeoutError"):
        return "Endpoint tidak bisa dihubungi; cek penulisan endpoint dan jaringan server."
    return None


def test_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uji koneksi storage dengan beberapa variasi addressing.

    Beberapa provider (mis. Backblaze) menutup koneksi saat kredensial salah,
    sehingga pesan aslinya hilang. Bila itu terjadi, kita panggil ListBuckets
    untuk mendapatkan kode error yang sebenarnya, lalu kembalikan hint yang
    bisa langsung ditindaklanjuti.
    """
    import time as _time

    provider = str(item.get("provider") or "")
    variants: List[Dict[str, Any]] = [
        {"path_style": bool(item.get("path_style")), "label": "sesuai konfigurasi"},
        {"path_style": not bool(item.get("path_style")), "label": "kebalikan path-style"},
    ]

    last_error = ""
    for variant in variants:
        started = _time.monotonic()
        try:
            candidate = dict(item)
            candidate["path_style"] = variant["path_style"]
            resolved = resolve(candidate, timeout=10)
            _probe(resolved, resolved.bucket)
            latency = int((_time.monotonic() - started) * 1000)
            result: Dict[str, Any] = {"ok": True, "latency_ms": latency}
            if variant["path_style"] != bool(item.get("path_style")):
                result["suggested"] = {"path_style": variant["path_style"]}
                result["note"] = "Berhasil dengan path-style " + ("aktif" if variant["path_style"] else "nonaktif") + "."
            return result
        except Exception as exc:
            last_error = type(exc).__name__ + ": " + str(exc)[:200]

    diagnosis = _diagnose(item)
    code = diagnosis.get("error_code")
    hint = _hint_for(str(code) if code else None, provider)
    return {
        "ok": False,
        "latency_ms": None,
        "error": (code + ": " + (diagnosis.get("error_message") or ""))[:240]
        if code
        else last_error,
        "error_code": code,
        "hint": hint,
    }


async def sync_mirrors(limit: int = 200) -> Dict[str, Any]:
    """Salin objek yang belum ada di mirror (dipanggil manual dari dashboard)."""
    import asyncio

    config = get_config()
    primary_item = None
    for item in config.get("items", []):
        if item.get("id") == config.get("primary_id"):
            primary_item = item
            break
    if not primary_item:
        return {"ok": False, "error": "primary belum diset"}

    def worker() -> Dict[str, Any]:
        primary = resolve(primary_item)
        copied = 0
        failed = 0
        skipped = 0
        for mirror_id in config.get("mirror_ids", []):
            mirror_item = next((i for i in config["items"] if i.get("id") == mirror_id), None)
            if not mirror_item:
                continue
            try:
                mirror = resolve(mirror_item)
            except Exception:
                failed += 1
                continue
            token = None
            while copied + skipped < limit:
                kwargs = {"Bucket": primary.bucket, "MaxKeys": 200}
                if primary.path_prefix:
                    kwargs["Prefix"] = primary.path_prefix
                if token:
                    kwargs["ContinuationToken"] = token
                listing = primary.client.list_objects_v2(**kwargs)
                for obj in listing.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith("/"):
                        continue
                    exists = True
                    try:
                        mirror.client.head_object(Bucket=mirror.bucket, Key=key)
                    except Exception:
                        exists = False
                    if exists:
                        skipped += 1
                        continue
                    try:
                        body = primary.client.get_object(Bucket=primary.bucket, Key=key)["Body"].read()
                        mirror.client.put_object(Bucket=mirror.bucket, Key=key, Body=body)
                        copied += 1
                    except Exception:
                        failed += 1
                    if copied + skipped >= limit:
                        break
                if not listing.get("IsTruncated"):
                    break
                token = listing.get("NextContinuationToken")
        return {"ok": True, "copied": copied, "skipped": skipped, "failed": failed}

    return await asyncio.get_event_loop().run_in_executor(None, worker)
