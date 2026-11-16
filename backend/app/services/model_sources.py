"""Sumber model Whisper multi-provider.

Satu manifest (`app/templates/model_sources.yml`) mendefinisikan semua
provider: field kredensial, adapter, cara restore, dan nama template Vast.
Modul ini memuat manifest tersebut, menyimpan konfigurasi provider aktif
(secret terenkripsi), serta menyediakan adapter dengan antarmuka seragam:

    adapter.list_items()    -> daftar folder/repo model + isi filenya
    adapter.delete(path)    -> hapus folder/repo (bila didukung)
    adapter.model_url(path) -> URL unduh model.bin (restore url_download)
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

MANIFEST_PATH = Path(__file__).resolve().parents[1] / "templates" / "model_sources.yml"
SETTING_KEY = "whisper_source"
RESTORE_SETTING_KEY = "whisper_restore"
ADAPTERS = {"gdrive", "dropbox", "b2", "s3", "huggingface"}
RESTORE_MODES = {"vast_cloud_copy", "url_download", "hf_snapshot"}


class SourceError(RuntimeError):
    """Kesalahan yang bisa ditampilkan apa adanya ke admin."""


@dataclass
class Provider:
    id: str
    label: str
    adapter: str
    icon: str = "bucket"
    color: str = ""
    restore_mode: str = "url_download"
    template_name: str = ""
    notebook: str = ""
    folder_url: str = ""
    description: str = ""
    hint: str = ""
    scan: bool = True
    can_delete: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    fields: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def secret_fields(self) -> List[str]:
        return [f["name"] for f in self.fields if f.get("type") == "secret"]

    @property
    def defaults(self) -> Dict[str, str]:
        return {
            str(f["name"]): str(f.get("default") or "")
            for f in self.fields
            if f.get("default")
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "adapter": self.adapter,
            "icon": self.icon,
            "color": self.color,
            "restore_mode": self.restore_mode,
            "template_name": self.template_name,
            "notebook": self.notebook,
            "folder_url": self.folder_url,
            "description": self.description,
            "hint": self.hint,
            "scan": self.scan,
            "can_delete": self.can_delete,
            "env": dict(self.env),
            "fields": [dict(f) for f in self.fields],
        }


_lock = threading.Lock()
_cache: Optional[Tuple[float, Dict[str, Provider], List[str]]] = None


def _read_manifest() -> Tuple[Dict[str, Provider], List[str]]:
    if not MANIFEST_PATH.is_file():
        raise SourceError(f"Manifest provider tidak ditemukan: {MANIFEST_PATH}")
    try:
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001 - pesan untuk admin
        raise SourceError(f"Manifest provider bukan YAML valid: {exc}") from exc

    warnings: List[str] = []
    found: Dict[str, Provider] = {}
    entries = raw.get("providers") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SourceError("Manifest provider tidak punya daftar `providers`.")

    templates_dir = MANIFEST_PATH.parent
    for entry in entries:
        if not isinstance(entry, dict):
            warnings.append("Ada entri provider yang bukan objek; dilewati.")
            continue
        pid = str(entry.get("id") or "").strip().lower()
        adapter = str(entry.get("adapter") or "").strip().lower()
        if not pid or not re.fullmatch(r"[a-z0-9_-]{2,32}", pid):
            warnings.append(f"Provider dengan id tidak valid dilewati: {pid!r}")
            continue
        if pid in found:
            warnings.append(f"Provider duplikat dilewati: {pid}")
            continue
        if adapter not in ADAPTERS:
            warnings.append(
                f"Provider '{pid}' memakai adapter tak dikenal ({adapter!r}); dilewati."
            )
            continue
        mode = str(entry.get("restore_mode") or "url_download").strip()
        if mode not in RESTORE_MODES:
            warnings.append(
                f"Provider '{pid}' punya restore_mode tidak dikenal ({mode!r}); dilewati."
            )
            continue
        fields: List[Dict[str, Any]] = []
        for item in entry.get("fields") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not re.fullmatch(r"[a-z0-9_]{2,40}", name):
                warnings.append(f"Field tidak valid di provider '{pid}': {name!r}")
                continue
            fields.append(
                {
                    "name": name,
                    "label": str(item.get("label") or name),
                    "type": "secret" if item.get("type") == "secret" else "text",
                    "required": bool(item.get("required", False)),
                    "default": str(item.get("default") or ""),
                    "help": str(item.get("help") or ""),
                    "max_length": int(item.get("max_length") or (512 if item.get("type") == "secret" else 400)),
                }
            )
        if not fields:
            warnings.append(f"Provider '{pid}' tidak punya field kredensial; dilewati.")
            continue
        notebook = str(entry.get("notebook") or "").strip()
        if notebook and not (templates_dir / notebook).is_file():
            warnings.append(
                f"Notebook '{notebook}' untuk provider '{pid}' belum ada di templates/."
            )
        found[pid] = Provider(
            id=pid,
            label=str(entry.get("label") or pid.title()),
            adapter=adapter,
            icon=str(entry.get("icon") or "bucket"),
            color=str(entry.get("color") or ""),
            restore_mode=mode,
            template_name=str(entry.get("vast_template_name") or f"Clipzy {pid.title()}"),
            notebook=notebook,
            folder_url=str(entry.get("folder_url") or ""),
            description=str(entry.get("description") or "").strip(),
            hint=str(entry.get("hint") or "").strip(),
            scan=bool(entry.get("scan", True)),
            can_delete=bool(entry.get("delete", True)),
            env={str(k): str(v) for k, v in (entry.get("env") or {}).items()},
            fields=fields,
        )
    if not found:
        raise SourceError("Manifest provider tidak berisi provider yang valid.")
    return found, warnings


def load_manifest(force: bool = False) -> Dict[str, Provider]:
    """Muat manifest YAML (cache berdasarkan mtime file)."""
    global _cache
    mtime = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.is_file() else 0.0
    with _lock:
        if not force and _cache and _cache[0] == mtime:
            return _cache[1]
        found, warnings = _read_manifest()
        for warning in warnings:
            logger.warning("manifest provider: %s", warning)
        _cache = (mtime, found, warnings)
        return found


def manifest_warnings() -> List[str]:
    load_manifest()
    return list(_cache[2]) if _cache else []


def providers() -> List[Provider]:
    return list(load_manifest().values())


def get_provider(provider_id: Optional[str]) -> Provider:
    items = load_manifest()
    pid = str(provider_id or "").strip().lower()
    if pid and pid in items:
        return items[pid]
    default_id = ""
    try:
        raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
        default_id = str(raw.get("default") or "").strip().lower()
    except Exception:  # noqa: BLE001
        default_id = ""
    if default_id in items:
        return items[default_id]
    return next(iter(items.values()))


def default_provider_id() -> str:
    return get_provider(None).id


def provider_for_template(name: str) -> Optional[Provider]:
    wanted = str(name or "").strip().lower()
    if not wanted:
        return None
    for provider in load_manifest().values():
        if provider.template_name.lower() == wanted:
            return provider
    return None


def notebook_path(provider_id: str) -> Path:
    provider = get_provider(provider_id)
    if not provider.notebook:
        raise SourceError(f"Provider '{provider.id}' tidak punya notebook Colab.")
    path = MANIFEST_PATH.parent / provider.notebook
    if not path.is_file():
        raise SourceError(f"Template notebook '{provider.notebook}' tidak ditemukan.")
    return path


# ---------------------------------------------------------------- konfigurasi
def mask_secret(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "•" * len(text)
    return f"{text[:4]}…{text[-4:]}"


async def _setting(db: AsyncSession) -> Dict[str, Any]:
    from app.services import platform_settings as ps

    raw = await ps.get_setting(db, SETTING_KEY, {})
    return raw if isinstance(raw, dict) else {}


async def get_source(db: AsyncSession) -> Dict[str, Any]:
    """Provider aktif + nilai kredensial yang tersimpan (secret disamarkan)."""
    stored = await _setting(db)
    provider = get_provider(stored.get("provider"))
    values = stored.get("values") if isinstance(stored.get("values"), dict) else {}
    merged: Dict[str, str] = {**provider.defaults}
    display: Dict[str, str] = {}
    for item in provider.fields:
        name = item["name"]
        raw = str(values.get(name) or "")
        plain = ""
        if raw:
            try:
                plain = decrypt_field(raw) if item.get("type") == "secret" else raw
            except Exception:  # noqa: BLE001
                plain = ""
        merged[name] = plain or merged.get(name, "")
        display[name] = mask_secret(plain) if item.get("type") == "secret" else plain
    return {
        "provider": provider.id,
        "provider_meta": provider.as_dict(),
        "values": display,
        "configured": all(
            merged.get(f["name"]) for f in provider.fields if f.get("required")
        ),
    }


async def save_source(
    db: AsyncSession,
    provider_id: str,
    values: Dict[str, Any],
    *,
    provider: Optional[Provider] = None,
    reset: bool = False,
) -> Dict[str, Any]:
    """Simpan kredensial provider aktif. Secret kosong = pertahankan nilai lama.

    `reset=True` menghapus nilai tersimpan (dipakai saat admin salah menempel
    lalu ingin mengisi ulang dari nol).
    """
    from app.services import platform_settings as ps

    provider = provider or get_provider(provider_id)
    stored = await _setting(db)
    previous = stored.get("values") if isinstance(stored.get("values"), dict) else {}
    incoming = values if isinstance(values, dict) else {}
    if reset and not any(str(value or "").strip() for value in incoming.values()):
        await ps.set_setting(
            db,
            SETTING_KEY,
            {
                "provider": provider.id,
                "values": {},
                "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
            },
        )
        await db.commit()
        return await get_source(db)
    if reset:
        previous = {}
    saved: Dict[str, str] = {}
    for item in provider.fields:
        name = item["name"]
        raw = incoming.get(name)
        text = str(raw).strip() if raw is not None else ""
        limit = int(item.get("max_length") or 0)
        if text and limit and len(text) > limit:
            if name == "app_secret" and text.startswith("sl.") and len(text) > 64:
                raise SourceError(
                    "Nilai di kolom 'App secret' terlihat seperti **access token "
                    "Dropbox** (diawali 'sl.' dan panjang). Tempel di kolom "
                    "'Access token (sl.…)', lalu isi App secret dengan nilai pendek "
                    "dari App Console → Settings."
                )
            raise SourceError(
                f"{provider.label}: '{item['label']}' terlalu panjang "
                f"({len(text)} karakter, maks {limit}). Kemungkinan Anda menempel "
                "nilai yang salah (token/JSON) — ambil ulang dari dashboard provider."
            )
        if item.get("type") == "secret":
            if text:
                saved[name] = encrypt_field(text)
            else:
                saved[name] = str(previous.get(name) or "")
        else:
            saved[name] = text or str(previous.get(name) or item.get("default") or "")
    missing = [f["label"] for f in provider.fields if f.get("required") and not saved.get(f["name"])]
    if missing:
        raise SourceError("Field wajib belum diisi: " + ", ".join(missing))

    record = {
        "provider": provider.id,
        "values": saved,
        "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
    }
    await ps.set_setting(db, SETTING_KEY, record)
    await db.commit()
    return await get_source(db)


async def resolved_values(
    db: AsyncSession, provider_id: Optional[str] = None
) -> Tuple[Provider, Dict[str, str]]:
    """Kredensial provider dalam bentuk asli (untuk adapter)."""
    stored = await _setting(db)
    provider = get_provider(provider_id or stored.get("provider"))
    values = stored.get("values") if isinstance(stored.get("values"), dict) else {}
    resolved: Dict[str, str] = {**provider.defaults}
    for item in provider.fields:
        name = item["name"]
        raw = str(values.get(name) or "")
        if not raw:
            continue
        if item.get("type") == "secret":
            try:
                resolved[name] = decrypt_field(raw)
            except Exception as exc:  # noqa: BLE001
                raise SourceError(f"Gagal membuka secret '{name}': {exc}") from exc
        else:
            resolved[name] = raw
    return provider, resolved


# Env restore dipakai `build_worker_env()` (sinkron) saat dispatch.
_restore_env: Dict[str, str] = {}


def restore_env() -> Dict[str, str]:
    return dict(_restore_env)


def set_restore_env(env: Optional[Dict[str, str]]) -> None:
    global _restore_env
    _restore_env = {str(k): str(v) for k, v in (env or {}).items() if str(v).strip()}


async def refresh_restore_env(db: AsyncSession) -> Dict[str, str]:
    """Muat env restore aktif dari platform settings (dipanggil saat startup)."""
    from app.services import platform_settings as ps

    raw = await ps.get_setting(db, RESTORE_SETTING_KEY, {})
    env = raw.get("env") if isinstance(raw, dict) else {}
    set_restore_env(env if isinstance(env, dict) else {})
    return restore_env()


# ------------------------------------------------------------------- adapter
class BaseAdapter:
    """Antarmuka seragam semua provider model."""

    def __init__(self, provider: Provider, values: Dict[str, str]) -> None:
        self.provider = provider
        self.values = values

    # -- util --
    def _value(self, name: str) -> str:
        text = str(self.values.get(name) or "").strip()
        if not text:
            field = next((f for f in self.provider.fields if f["name"] == name), None)
            label = field["label"] if field else name
            raise SourceError(f"{self.provider.label}: '{label}' belum diisi.")
        return text

    def _root(self) -> str:
        return str(self.values.get("root") or "").strip().strip("/")

    async def test(self) -> Dict[str, Any]:
        items = await self.list_items()
        return {"ok": True, "count": len(items), "items": [item["label"] for item in items[:10]]}

    async def list_items(self) -> List[Dict[str, Any]]:  # pragma: no cover - abstrak
        raise SourceError(f"Adapter {self.provider.adapter} tidak mendukung scan.")

    async def delete(self, remote_path: str) -> int:  # pragma: no cover - abstrak
        raise SourceError(f"Adapter {self.provider.adapter} tidak mendukung hapus.")

    async def model_url(self, remote_path: str) -> str:
        raise SourceError(
            f"Provider {self.provider.label} tidak memakai restore URL; "
            "model diunduh langsung oleh worker."
        )


class GDriveAdapter(BaseAdapter):
    """Provider lama: Google Drive (service account)."""

    def _drive(self):
        from app.core.config import get_settings
        from app.services.drive_service import DriveError, DriveService

        base = get_settings()
        updates: Dict[str, Any] = {}
        if self.values.get("service_account_b64"):
            updates["GDRIVE_SERVICE_ACCOUNT_B64"] = self.values["service_account_b64"]
        if self.values.get("folder_id"):
            updates["GDRIVE_FOLDER_ID"] = self.values["folder_id"]
        if updates:
            updates["GDRIVE_ENABLED"] = True
        drive = DriveService()
        if updates:
            try:
                drive.settings = base.model_copy(update=updates)
                drive._client = None
            except Exception:  # noqa: BLE001 - fallback ke env
                drive = DriveService()
        if not drive.configured:
            raise SourceError(
                "Google Drive belum siap. Isi service account (base64) + folder ID, "
                "atau set GDRIVE_SERVICE_ACCOUNT_B64/GDRIVE_FOLDER_ID di env backend."
            )
        return drive, DriveError

    async def list_items(self) -> List[Dict[str, Any]]:
        drive, DriveError = self._drive()
        try:
            root = await drive.get_file(drive.folder_id)
            if root.get("mimeType") != "application/vnd.google-apps.folder":
                raise SourceError("Folder ID Google Drive bukan sebuah folder.")
            folders = await drive.list_children(drive.folder_id, folders_only=True)
            items: List[Dict[str, Any]] = []
            for folder in folders:
                folder_id = str(folder.get("id") or "").strip()
                name = str(folder.get("name") or "").strip()
                if not folder_id or not name or name.startswith("."):
                    continue
                files = await drive.list_children(folder_id)
                items.append(
                    {
                        "remote_id": folder_id,
                        "label": name,
                        "remote_path": drive.path_for(name),
                        "files": [
                            {
                                "name": str(item.get("name") or ""),
                                "size": int(item.get("size") or 0),
                            }
                            for item in files
                            if str(item.get("name") or "")
                        ],
                    }
                )
            return items
        except SourceError:
            raise
        except DriveError as exc:
            raise SourceError(str(exc)) from exc

    async def delete(self, remote_path: str) -> int:
        drive, DriveError = self._drive()
        folder_id = str(remote_path or "").strip()
        if not folder_id:
            raise SourceError("ID folder Google Drive kosong.")
        try:
            return int(await drive.delete_tree(folder_id))
        except DriveError as exc:
            raise SourceError(str(exc)) from exc


class DropboxAdapter(BaseAdapter):
    """Dropbox: folder root berisi subfolder model CT2.

    Dua mode autentikasi (dokumentasi Dropbox OAuth 2):
    1. **Access token** (`sl.…`) — langsung dipakai untuk semua panggilan API,
       tetapi kedaluwarsa ±4 jam.
    2. **Refresh token + App key + App secret** — SDK Dropbox meminta access
       token baru otomatis saat token lama habis (disarankan untuk produksi).
    """

    def auth_mode(self) -> str:
        if str(self.values.get("access_token") or "").strip():
            return "access"
        if (
            str(self.values.get("app_key") or "").strip()
            and str(self.values.get("app_secret") or "").strip()
            and str(self.values.get("refresh_token") or "").strip()
        ):
            return "refresh"
        raise SourceError(
            "Dropbox belum siap: isi **Access token** (sl.…) ATAU "
            "**App key + App secret + Refresh token**. "
            "App key/secret saja tidak bisa dipakai untuk upload — keduanya hanya "
            "untuk meminta access token baru."
        )

    def _client(self):
        try:
            import dropbox
        except ImportError as exc:  # pragma: no cover - dependency opsional
            raise SourceError(
                "Library python 'dropbox' belum terpasang di backend "
                "(pip install dropbox) — rebuild image backend."
            ) from exc
        mode = self.auth_mode()
        if mode == "access":
            return dropbox.Dropbox(
                oauth2_access_token=str(self.values.get("access_token") or "").strip(),
                timeout=60,
            )
        return dropbox.Dropbox(
            oauth2_refresh_token=self._value("refresh_token"),
            app_key=self._value("app_key"),
            app_secret=self._value("app_secret"),
            timeout=60,
        )

    def _root_path(self) -> str:
        root = str(self.values.get("root") or "").strip()
        if not root:
            return ""
        return root if root.startswith("/") else "/" + root

    def _list_sync(self) -> List[Dict[str, Any]]:
        import dropbox

        dbx = self._client()
        items: List[Dict[str, Any]] = []
        listing = dbx.files_list_folder(self._root_path(), recursive=False)
        folders = [e for e in listing.entries if isinstance(e, dropbox.files.FolderMetadata)]
        while listing.has_more:
            listing = dbx.files_list_folder_continue(listing.cursor)
            folders.extend(
                e for e in listing.entries if isinstance(e, dropbox.files.FolderMetadata)
            )
        for folder in folders:
            name = folder.name
            if not name or name.startswith("."):
                continue
            child = dbx.files_list_folder(folder.path_lower, recursive=False)
            files = [
                {"name": e.name, "size": int(getattr(e, "size", 0) or 0)}
                for e in child.entries
                if isinstance(e, dropbox.files.FileMetadata)
            ]
            items.append(
                {
                    "remote_id": folder.id,
                    "label": name,
                    "remote_path": folder.path_display or folder.path_lower,
                    "files": files,
                }
            )
        return items

    async def list_items(self) -> List[Dict[str, Any]]:
        import asyncio

        try:
            return await asyncio.to_thread(self._list_sync)
        except SourceError:
            raise
        except Exception as exc:  # noqa: BLE001 - pesan Dropbox
            raise SourceError(f"Dropbox gagal membaca folder: {str(exc)[:300]}") from exc

    async def delete(self, remote_path: str) -> int:
        import asyncio

        path = str(remote_path or "").strip()
        if not path:
            raise SourceError("Path Dropbox kosong.")
        try:
            await asyncio.to_thread(self._client().files_delete_v2, path)
            return 1
        except Exception as exc:  # noqa: BLE001
            raise SourceError(f"Dropbox gagal menghapus {path}: {str(exc)[:300]}") from exc

    async def model_url(self, remote_path: str) -> str:
        import asyncio

        path = str(remote_path or "").strip().rstrip("/") + "/model.bin"
        try:
            meta = await asyncio.to_thread(self._client().files_get_temporary_link, path)
            return str(meta.link)
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"Dropbox gagal membuat tautan unduh {path}: {str(exc)[:300]}"
            ) from exc

    async def test(self) -> Dict[str, Any]:
        import asyncio

        try:
            await asyncio.to_thread(self._client().users_get_current_account)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "expired_access_token" in message or "invalid_access_token" in message:
                raise SourceError(
                    "Access token Dropbox tidak valid/kedaluwarsa (umur token hanya "
                    "±4 jam). Buat token baru di App Console → Settings → "
                    "Generated access token, ATAU pakai App key + App secret + "
                    "Refresh token agar SDK memperbarui token otomatis."
                ) from exc
            if "invalid_client" in message:
                raise SourceError(
                    "Dropbox menolak App key/App secret (invalid_client). App secret "
                    "±15–30 karakter — access token/refresh token harus diisi di "
                    "kolomnya masing-masing. Ambil ulang di App Console → Settings."
                ) from exc
            if "invalid_grant" in message:
                raise SourceError(
                    "Refresh token Dropbox tidak valid/expired. Jalankan ulang "
                    "notebook Colab (cell otorisasi) untuk membuat refresh token baru."
                ) from exc
            raise SourceError(f"Dropbox menolak kredensial: {message[:300]}") from exc
        result = await super().test()
        result["mode"] = self.auth_mode()
        return result


class S3Adapter(BaseAdapter):
    """Backblaze B2 dan Amazon S3 (bucket S3-compatible)."""

    def _is_b2(self) -> bool:
        return self.provider.adapter == "b2"

    def _endpoint(self) -> Optional[str]:
        endpoint = str(self.values.get("endpoint") or "").strip().rstrip("/")
        return endpoint or None

    def _client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover
            raise SourceError("boto3 belum terpasang di backend.") from exc
        if self._is_b2():
            key_id = self._value("key_id")
            secret = self._value("app_key")
        else:
            key_id = self._value("access_key")
            secret = self._value("secret_key")
        region = str(self.values.get("region") or "").strip()
        if not region:
            region = "auto" if self._is_b2() else "us-east-1"
        if self._is_b2():
            match = re.search(r"s3[.-]([a-z0-9-]+)\.backblazeb2\.com", self._endpoint() or "")
            if match:
                region = match.group(1)
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint(),
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if self._is_b2() else "auto"},
                retries={"max_attempts": 2},
            ),
        )

    def _prefix(self, path: str = "") -> str:
        root = self._root()
        parts = [p for p in (root, str(path or "").strip("/")) if p]
        return "/".join(parts).strip("/")

    def _list_sync(self) -> List[Dict[str, Any]]:
        client = self._client()
        bucket = self._value("bucket")
        base = self._prefix()
        prefix = base + "/" if base else ""
        items: List[Dict[str, Any]] = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
            for common in page.get("CommonPrefixes") or []:
                path = str(common.get("Prefix") or "").rstrip("/")
                name = path.split("/")[-1]
                if not name or name.startswith("."):
                    continue
                files = [
                    {
                        "name": str(obj.get("Key") or "").split("/")[-1],
                        "size": int(obj.get("Size") or 0),
                    }
                    for obj in client.list_objects_v2(
                        Bucket=bucket, Prefix=path + "/"
                    ).get("Contents", [])
                ]
                items.append(
                    {"remote_id": path, "label": name, "remote_path": path, "files": files}
                )
        return items

    async def list_items(self) -> List[Dict[str, Any]]:
        import asyncio

        try:
            return await asyncio.to_thread(self._list_sync)
        except SourceError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"{self.provider.label} gagal membaca bucket: {str(exc)[:300]}"
            ) from exc

    async def delete(self, remote_path: str) -> int:
        import asyncio

        client = self._client()
        bucket = self._value("bucket")
        prefix = self._prefix(remote_path) + "/"

        def _delete() -> int:
            keys: List[Dict[str, str]] = []
            for page in client.get_paginator("list_objects_v2").paginate(
                Bucket=bucket, Prefix=prefix
            ):
                for obj in page.get("Contents") or []:
                    keys.append({"Key": str(obj.get("Key"))})
            removed = 0
            for start in range(0, len(keys), 1000):
                chunk = keys[start : start + 1000]
                response = client.delete_objects(
                    Bucket=bucket, Delete={"Objects": chunk, "Quiet": True}
                )
                removed += len(chunk) - len(response.get("Errors") or [])
            return removed

        try:
            return int(await asyncio.to_thread(_delete))
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"{self.provider.label} gagal menghapus: {str(exc)[:300]}"
            ) from exc

    async def model_url(self, remote_path: str) -> str:
        import asyncio

        client = self._client()
        key = self._prefix(remote_path) + "/model.bin"
        try:
            return await asyncio.to_thread(
                client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._value("bucket"), "Key": key},
                ExpiresIn=6 * 3600,
            )
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"{self.provider.label} gagal membuat URL: {str(exc)[:300]}"
            ) from exc

    async def test(self) -> Dict[str, Any]:
        import asyncio

        try:
            await asyncio.to_thread(self._client().head_bucket, Bucket=self._value("bucket"))
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"{self.provider.label} menolak bucket: {str(exc)[:300]}"
            ) from exc
        return await super().test()


class HuggingFaceAdapter(BaseAdapter):
    """Hugging Face: satu repo = satu model (worker unduh langsung)."""

    def _api(self):
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:  # pragma: no cover
            raise SourceError("Library 'huggingface_hub' belum terpasang di backend.") from exc
        return HfApi(token=str(self.values.get("hf_token") or "").strip() or None)

    async def list_items(self) -> List[Dict[str, Any]]:
        import asyncio

        repo = self._value("repo_id")
        try:
            info = await asyncio.to_thread(self._api().model_info, repo, files_metadata=True)
        except Exception as exc:  # noqa: BLE001
            raise SourceError(
                f"Hugging Face gagal membaca repo {repo}: {str(exc)[:300]}"
            ) from exc
        files = [
            {
                "name": str(getattr(sibling, "rfilename", "")),
                "size": int(getattr(sibling, "size", 0) or 0),
            }
            for sibling in (getattr(info, "siblings", None) or [])
            if getattr(sibling, "rfilename", "")
        ]
        return [
            {
                "remote_id": repo,
                "label": repo.split("/")[-1],
                "remote_path": repo,
                "files": files,
            }
        ]

    async def delete(self, remote_path: str) -> int:
        raise SourceError(
            "Hugging Face bersifat read-only dari Clipzi; hapus repo manual di huggingface.co."
        )


_ADAPTER_CLASSES = {
    "gdrive": GDriveAdapter,
    "dropbox": DropboxAdapter,
    "b2": S3Adapter,
    "s3": S3Adapter,
    "huggingface": HuggingFaceAdapter,
}


def build_adapter(provider: Provider, values: Dict[str, str]) -> BaseAdapter:
    cls = _ADAPTER_CLASSES.get(provider.adapter)
    if cls is None:
        raise SourceError(f"Adapter '{provider.adapter}' tidak tersedia di backend.")
    return cls(provider, values)


async def adapter_for(db: AsyncSession, provider_id: Optional[str] = None) -> BaseAdapter:
    provider, values = await resolved_values(db, provider_id)
    return build_adapter(provider, values)


async def scan_items(
    db: AsyncSession, provider_id: Optional[str] = None
) -> Tuple[Provider, List[Dict[str, Any]]]:
    adapter = await adapter_for(db, provider_id)
    return adapter.provider, await adapter.list_items()


async def test_source(
    db: AsyncSession,
    provider_id: Optional[str] = None,
    values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Uji koneksi tanpa menyimpan: kredensial baru di atas nilai tersimpan."""
    provider, stored = await resolved_values(db, provider_id)
    if values:
        for field in provider.fields:
            name = field["name"]
            text = str(values.get(name) or "").strip()
            if not text:
                continue
            limit = int(field.get("max_length") or 0)
            if limit and len(text) > limit:
                raise SourceError(
                    f"{provider.label}: '{field['label']}' terlalu panjang "
                    f"({len(text)} karakter, maks {limit}). Salin ulang nilainya."
                )
            stored[name] = text
    adapter = build_adapter(provider, stored)
    result = await adapter.test()
    result.update({"provider": provider.id, "label": provider.label})
    return result


async def delete_remote(
    db: AsyncSession, provider_id: str, remote_path: str
) -> Tuple[Provider, int]:
    adapter = await adapter_for(db, provider_id)
    if not adapter.provider.can_delete:
        raise SourceError(f"{adapter.provider.label} tidak mendukung hapus dari Clipzi.")
    return adapter.provider, int(await adapter.delete(remote_path))


MODEL_WORKSPACE = "/workspace/whisper_model"
# Di Vast, /workspace dibuat root -> worker (user clipzi) tidak bisa menulis.
# Provider non-Drive mengunduh model ke path yang pasti writable.
MODEL_WORKSPACE_WRITABLE = "/app/whisper_model"


async def restore_plan(
    db: AsyncSession, provider_id: str, remote_path: str
) -> Dict[str, Any]:
    """Rencana restore model untuk provider terpilih (env + config Vast)."""
    provider = get_provider(provider_id)
    if provider.restore_mode == "vast_cloud_copy":
        return {
            "mode": provider.restore_mode,
            "env": {},
            "config": {
                "restore_enabled": True,
                "restore_src": remote_path,
                "restore_dst": MODEL_WORKSPACE,
                "restore_model_path": MODEL_WORKSPACE,
            },
        }
    if provider.restore_mode == "url_download":
        adapter = await adapter_for(db, provider.id)
        url = await adapter.model_url(remote_path)
        env = {
            "CLIPZI_MODEL_SOURCE": provider.id,
            "CLIPZI_MODEL_URL": url,
            "CLIPZI_RESTORE_TIMEOUT": "600",
            "CLIPZI_RESTORE_MODEL_PATH": MODEL_WORKSPACE_WRITABLE,
            "GPU_WHISPER_MODEL": MODEL_WORKSPACE_WRITABLE,
        }
        return {
            "mode": provider.restore_mode,
            "env": env,
            "config": {
                "restore_enabled": False,
                "restore_model_path": MODEL_WORKSPACE_WRITABLE,
            },
        }
    env = {
        "CLIPZI_MODEL_SOURCE": "huggingface",
        "CLIPZI_HF_REPO": remote_path,
        "CLIPZI_RESTORE_MODEL_PATH": MODEL_WORKSPACE_WRITABLE,
        "GPU_WHISPER_MODEL": MODEL_WORKSPACE_WRITABLE,
    }
    try:
        _, values = await resolved_values(db, provider.id)
        token = str(values.get("hf_token") or "").strip()
    except Exception:  # noqa: BLE001 - token opsional untuk repo publik
        token = ""
    if token:
        env["HF_TOKEN"] = token
    return {
        "mode": provider.restore_mode,
        "env": env,
        "config": {
            "restore_enabled": False,
            "restore_model_path": MODEL_WORKSPACE_WRITABLE,
        },
    }


async def save_restore_env(
    db: AsyncSession, provider_id: str, env: Dict[str, str]
) -> Dict[str, str]:
    """Simpan env restore aktif supaya dispatch berikutnya memakainya."""
    from app.services import platform_settings as ps

    cleaned = {str(k): str(v) for k, v in (env or {}).items() if str(v).strip()}
    await ps.set_setting(
        db,
        RESTORE_SETTING_KEY,
        {
            "provider": get_provider(provider_id).id,
            "env": cleaned,
            "updated_at": __import__("datetime").datetime.utcnow().isoformat(),
        },
    )
    await db.commit()
    set_restore_env(cleaned)
    return restore_env()


def public_view(active_provider: str) -> Dict[str, Any]:
    """Ringkasan manifest untuk UI (tanpa secret)."""
    items: List[Dict[str, Any]] = []
    for provider in providers():
        item = provider.as_dict()
        item["active"] = provider.id == active_provider
        items.append(item)
    return {
        "providers": items,
        "default": default_provider_id(),
        "active": active_provider,
        "warnings": manifest_warnings(),
    }


__all__ = [
    "MODEL_WORKSPACE",
    "Provider",
    "SourceError",
    "adapter_for",
    "build_adapter",
    "default_provider_id",
    "delete_remote",
    "get_provider",
    "get_source",
    "load_manifest",
    "manifest_warnings",
    "notebook_path",
    "providers",
    "public_view",
    "refresh_restore_env",
    "resolved_values",
    "restore_env",
    "restore_plan",
    "save_restore_env",
    "save_source",
    "scan_items",
    "set_restore_env",
    "test_source",
]


