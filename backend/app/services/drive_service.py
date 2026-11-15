"""Klien Google Drive minimal untuk registry model Whisper.

Autentikasi memakai service account (bukan OAuth user). Service account hanya
dipakai untuk *membaca/menghapus* folder model; upload dilakukan oleh akun
Google pemilik Drive lewat Colab/OAuth karena service account tidak punya kuota
penyimpanan sendiri.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

FOLDER_MIME = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,size,modifiedTime,md5Checksum,webViewLink,parents"


class DriveError(RuntimeError):
    """Kesalahan konfigurasi atau operasi Google Drive."""


def _decode_service_account(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise DriveError("Service account Drive belum diisi.")
    try:
        return json.loads(base64.b64decode(text))
    except Exception as exc:  # noqa: BLE001 - pesan dibuat untuk admin
        raise DriveError("GDRIVE_SERVICE_ACCOUNT_B64 tidak valid (bukan base64 JSON).") from exc


class DriveService:
    """Wrapper sinkron Google Drive API yang aman dipanggil dari async code."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Optional[Any] = None

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.settings, "GDRIVE_ENABLED", False))

    @property
    def folder_id(self) -> str:
        return str(getattr(self.settings, "GDRIVE_FOLDER_ID", "") or "").strip()

    @property
    def shared_drive_id(self) -> str:
        return str(getattr(self.settings, "GDRIVE_SHARED_DRIVE_ID", "") or "").strip()

    @property
    def root_path(self) -> str:
        return str(
            getattr(self.settings, "GDRIVE_VAST_ROOT_PATH", "/vast-backup/Clipzy/whisper_models")
            or "/vast-backup/Clipzy/whisper_models"
        ).rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.folder_id
            and (
                getattr(self.settings, "GDRIVE_SERVICE_ACCOUNT_B64", None)
                or getattr(self.settings, "GDRIVE_SERVICE_ACCOUNT_FILE", None)
            )
        )

    def _credentials_info(self) -> Optional[Dict[str, Any]]:
        raw = str(getattr(self.settings, "GDRIVE_SERVICE_ACCOUNT_B64", "") or "").strip()
        if raw:
            return _decode_service_account(raw)
        path = str(getattr(self.settings, "GDRIVE_SERVICE_ACCOUNT_FILE", "") or "").strip()
        if path:
            file_path = Path(path)
            if not file_path.is_file():
                raise DriveError(f"File service account tidak ditemukan: {path}")
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise DriveError("File service account bukan JSON yang valid.") from exc
        return None

    def service_account_email(self) -> str:
        info = self._credentials_info() or {}
        return str(info.get("client_email") or "").strip()

    def _build(self) -> Any:
        if not self.enabled:
            raise DriveError("Google Drive dinonaktifkan (GDRIVE_ENABLED=false).")
        if not self.folder_id:
            raise DriveError("GDRIVE_FOLDER_ID belum diisi.")
        info = self._credentials_info()
        if not info:
            raise DriveError(
                "Kredensial Drive belum diisi. Set GDRIVE_SERVICE_ACCOUNT_B64 "
                "atau GDRIVE_SERVICE_ACCOUNT_FILE."
            )
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - dependency image
            raise DriveError(
                "Paket google-api-python-client/google-auth belum terpasang."
            ) from exc

        credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        self._client = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        return self._client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._build()
        return self._client

    def _list_sync(
        self, parent_id: str, *, folders_only: bool = False, page_size: int = 1000
    ) -> List[Dict[str, Any]]:
        query = f"'{parent_id}' in parents and trashed=false"
        if folders_only:
            query += f" and mimeType='{FOLDER_MIME}'"
        items: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {
                "q": query,
                "pageSize": min(max(int(page_size), 1), 1000),
                "fields": f"nextPageToken,files({FILE_FIELDS})",
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if self.shared_drive_id:
                kwargs["corpora"] = "drive"
                kwargs["driveId"] = self.shared_drive_id
            if page_token:
                kwargs["pageToken"] = page_token
            response = self.client.files().list(**kwargs).execute()
            items.extend(response.get("files", []) or [])
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return items

    async def list_children(
        self, parent_id: str, *, folders_only: bool = False
    ) -> List[Dict[str, Any]]:
        try:
            return await asyncio.to_thread(
                self._list_sync, parent_id, folders_only=folders_only
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Drive list %s gagal: %s", parent_id, exc)
            raise DriveError(f"Gagal membaca folder Drive: {exc}") from exc

    def _get_sync(self, file_id: str) -> Dict[str, Any]:
        return (
            self.client.files()
            .get(
                fileId=file_id,
                fields=FILE_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )

    async def get_file(self, file_id: str) -> Dict[str, Any]:
        try:
            return await asyncio.to_thread(self._get_sync, file_id)
        except Exception as exc:  # noqa: BLE001
            raise DriveError(f"Folder Drive tidak dapat diakses: {exc}") from exc

    def _create_folder_sync(self, name: str, parent_id: str) -> Dict[str, Any]:
        body = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_id],
        }
        return (
            self.client.files()
            .create(
                body=body,
                fields=FILE_FIELDS,
                supportsAllDrives=True,
            )
            .execute()
        )

    async def create_folder(self, name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        parent = (parent_id or self.folder_id).strip()
        if not parent:
            raise DriveError("Parent folder Drive belum diisi.")
        try:
            return await asyncio.to_thread(self._create_folder_sync, name, parent)
        except Exception as exc:  # noqa: BLE001
            raise DriveError(f"Gagal membuat folder Drive: {exc}") from exc

    def _delete_sync(self, file_id: str) -> None:
        self.client.files().delete(
            fileId=file_id,
            supportsAllDrives=True,
        ).execute()

    def _delete_tree_sync(self, file_id: str) -> int:
        """Hapus folder beserta isinya; return jumlah objek yang dihapus."""
        removed = 0
        children = self._list_sync(file_id)
        for child in children:
            child_id = str(child.get("id") or "")
            if not child_id:
                continue
            if child.get("mimeType") == FOLDER_MIME:
                removed += self._delete_tree_sync(child_id)
            else:
                self._delete_sync(child_id)
                removed += 1
        self._delete_sync(file_id)
        return removed + 1

    async def delete_tree(self, file_id: str) -> int:
        try:
            return await asyncio.to_thread(self._delete_tree_sync, file_id)
        except Exception as exc:  # noqa: BLE001
            raise DriveError(f"Gagal menghapus folder Drive: {exc}") from exc

    def path_for(self, folder_name: str) -> str:
        return f"{self.root_path}/{str(folder_name or '').strip()}"


__all__ = ["DriveError", "DriveService", "FOLDER_MIME"]


