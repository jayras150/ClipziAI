"""Registry + validasi model Whisper CT2 di Google Drive.

Alur: admin menekan **Scan Drive**, backend membaca folder di bawah
`GDRIVE_FOLDER_ID`, memvalidasi file CT2, lalu menyimpan metadata ke tabel
`whisper_models`. Saat model diaktifkan, `VAST_RESTORE_SRC` diarahkan ke folder
model tersebut sehingga worker berikutnya menyalin model yang benar.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whisper_model import WhisperModel
from app.services.drive_service import DriveError, DriveService, FOLDER_MIME

CT2_REQUIRED = ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json")
CT2_VOCAB = ("vocabulary.json", "vocabulary.txt")
PYTORCH_MARKERS = ("model.safetensors", "pytorch_model.bin")
TENSORFLOW_MARKERS = ("tf_model.h5", "model.ckpt.index")
MODEL_WORKSPACE = "/workspace/whisper_model"


def normalize_slug(value: str) -> str:
    """Slug aman untuk URL/DB; nama folder tetap disimpan terpisah di label."""
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower())
    return text.strip("-")[:80]


def _size(files: List[Dict[str, Any]]) -> int:
    total = 0
    for item in files:
        try:
            total += int(item.get("size") or 0)
        except (TypeError, ValueError):
            continue
    return total


def inspect_files(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validasi isi folder model tanpa mengunduh model.

    Return `status` (`available`, `missing`, `invalid`), `validation_error`,
    `size_bytes`, `file_count`, dan daftar nama file.
    """
    names: List[str] = []
    for item in files:
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    lower = {name.lower() for name in names}
    size_bytes = _size(files)
    result: Dict[str, Any] = {
        "status": "missing",
        "validation_error": None,
        "size_bytes": size_bytes,
        "file_count": len(names),
        "files": sorted(names),
    }
    if not names:
        result["validation_error"] = "Folder model kosong."
        return result

    if any(marker in lower for marker in TENSORFLOW_MARKERS):
        result["status"] = "invalid"
        result["validation_error"] = (
            "Model TensorFlow terdeteksi. Konversi ke CT2 terlebih dahulu; "
            "TensorFlow tidak didukung worker."
        )
        return result

    required_missing = [name for name in CT2_REQUIRED if name not in lower]
    has_vocab = any(name in lower for name in CT2_VOCAB)
    if "model.bin" in lower:
        if required_missing:
            result["status"] = "invalid"
            result["validation_error"] = (
                "Model CT2 tidak lengkap: " + ", ".join(required_missing)
            )
            return result
        if not has_vocab:
            result["status"] = "invalid"
            result["validation_error"] = (
                "Model CT2 tidak punya vocabulary.json/vocabulary.txt."
            )
            return result
        result["status"] = "available"
        return result

    if any(marker in lower for marker in PYTORCH_MARKERS):
        result["status"] = "invalid"
        result["validation_error"] = (
            "Model PyTorch terdeteksi. Jalankan Colab downloader untuk "
            "mengonversi ke CT2 sebelum dipakai worker."
        )
        return result

    result["status"] = "invalid"
    result["validation_error"] = (
        "Tidak ada model.bin (CT2) di folder. File yang dikenal: "
        + ", ".join(sorted(names)[:8])
    )
    return result


def model_to_dict(row: WhisperModel) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "label": row.label,
        "drive_folder_id": row.drive_folder_id,
        "drive_path": row.drive_path,
        "model_type": row.model_type,
        "status": row.status,
        "validation_error": row.validation_error,
        "size_bytes": int(row.size_bytes or 0),
        "file_count": int(row.file_count or 0),
        "files": row.files or [],
        "is_active": bool(row.is_active),
        "last_scanned_at": row.last_scanned_at.isoformat()
        if row.last_scanned_at
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }

async def list_models(db: AsyncSession) -> List[WhisperModel]:
    result = await db.execute(
        select(WhisperModel).order_by(
            WhisperModel.is_active.desc(),
            WhisperModel.status.asc(),
            WhisperModel.label.asc(),
        )
    )
    return list(result.scalars().all())


def _unique_slug(base: str, folder_id: str, used: set[str]) -> str:
    slug = normalize_slug(base) or "model"
    if slug not in used:
        return slug
    candidate = f"{slug}-{folder_id[:6]}"
    counter = 2
    while candidate in used:
        candidate = f"{slug}-{folder_id[:6]}-{counter}"
        counter += 1
    return candidate


async def scan_models(db: AsyncSession) -> Dict[str, Any]:
    """Scan folder root Drive dan sinkronkan registry.

    Folder yang hilang dari Drive tidak dihapus otomatis; statusnya diubah
    menjadi `missing` agar admin masih bisa melihat riwayat dan menghapusnya.
    """
    drive = DriveService()
    if not drive.configured:
        raise DriveError(
            "Google Drive belum siap. Isi GDRIVE_SERVICE_ACCOUNT_B64, "
            "GDRIVE_FOLDER_ID, dan GDRIVE_ENABLED=true."
        )

    root = await drive.get_file(drive.folder_id)
    if root.get("mimeType") != FOLDER_MIME:
        raise DriveError("GDRIVE_FOLDER_ID bukan sebuah folder Drive.")

    folders = await drive.list_children(drive.folder_id, folders_only=True)
    existing = list((await db.execute(select(WhisperModel))).scalars().all())
    by_folder = {row.drive_folder_id: row for row in existing}
    used_slugs = {row.slug for row in existing}
    seen: set[str] = set()
    now = datetime.utcnow()
    created = 0
    updated = 0

    for folder in folders:
        folder_id = str(folder.get("id") or "").strip()
        folder_name = str(folder.get("name") or "").strip()
        if not folder_id or not folder_name:
            continue
        seen.add(folder_id)
        try:
            files = await drive.list_children(folder_id)
            info = inspect_files(files)
        except DriveError as exc:
            info = {
                "status": "error",
                "validation_error": str(exc)[:1000],
                "size_bytes": 0,
                "file_count": 0,
                "files": [],
            }

        row = by_folder.get(folder_id)
        if row is None:
            row = WhisperModel(
                slug=_unique_slug(folder_name, folder_id, used_slugs),
                label=folder_name,
                drive_folder_id=folder_id,
                drive_path=drive.path_for(folder_name),
                model_type="ct2",
                status=str(info["status"]),
                validation_error=info.get("validation_error"),
                size_bytes=int(info.get("size_bytes") or 0),
                file_count=int(info.get("file_count") or 0),
                files=info.get("files") or [],
                is_active=False,
                last_scanned_at=now,
            )
            db.add(row)
            used_slugs.add(row.slug)
            created += 1
        else:
            row.label = row.label or folder_name
            row.drive_path = drive.path_for(folder_name)
            row.model_type = "ct2"
            row.status = str(info["status"])
            row.validation_error = info.get("validation_error")
            row.size_bytes = int(info.get("size_bytes") or 0)
            row.file_count = int(info.get("file_count") or 0)
            row.files = info.get("files") or []
            row.last_scanned_at = now
            updated += 1

    missing = 0
    for row in existing:
        if row.drive_folder_id in seen:
            continue
        row.status = "missing"
        row.validation_error = "Folder model tidak ditemukan di Drive."
        row.last_scanned_at = now
        missing += 1

    await db.commit()
    rows = await list_models(db)
    return {
        "created": created,
        "updated": updated,
        "missing": missing,
        "total": len(rows),
        "items": [model_to_dict(row) for row in rows],
    }

async def activate_model(db: AsyncSession, model_id: Any) -> WhisperModel:
    """Aktifkan satu model + arahkan restore Vast ke folder model tersebut."""
    row = await db.get(WhisperModel, model_id)
    if row is None:
        raise ValueError("Model tidak ditemukan.")
    if row.status != "available":
        raise ValueError(
            "Model belum valid/available. Perbaiki file CT2 lalu scan ulang."
        )
    if not row.drive_path:
        raise ValueError("Path Drive model kosong.")

    await db.execute(update(WhisperModel).values(is_active=False))
    row.is_active = True
    await db.flush()

    from app.services import vast_config

    try:
        await vast_config.save_vast_config(
            db,
            {
                "restore_enabled": True,
                "restore_src": row.drive_path,
                "restore_dst": MODEL_WORKSPACE,
                "restore_model_path": MODEL_WORKSPACE,
            },
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    await db.refresh(row)
    return row


async def delete_model(
    db: AsyncSession, model_id: Any, *, delete_drive: bool = False
) -> Dict[str, Any]:
    """Hapus registry; opsional hapus folder Drive beserta isinya."""
    row = await db.get(WhisperModel, model_id)
    if row is None:
        raise ValueError("Model tidak ditemukan.")
    if row.is_active:
        raise ValueError("Model sedang aktif. Aktifkan model lain sebelum menghapus.")

    removed = 0
    if delete_drive and row.status != "missing":
        drive = DriveService()
        if not drive.configured:
            raise DriveError("Google Drive belum siap; tidak bisa menghapus folder.")
        removed = await drive.delete_tree(row.drive_folder_id)

    await db.delete(row)
    await db.commit()
    return {"deleted": True, "drive_objects_removed": removed}


async def drive_status() -> Dict[str, Any]:
    """Ringkasan koneksi Drive untuk header UI admin."""
    drive = DriveService()
    email = ""
    error = ""
    try:
        email = drive.service_account_email()
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    return {
        "configured": drive.configured,
        "enabled": drive.enabled,
        "folder_id": drive.folder_id,
        "root_path": drive.root_path,
        "service_account_email": email,
        "error": error,
    }


__all__ = [
    "CT2_REQUIRED",
    "MODEL_WORKSPACE",
    "activate_model",
    "delete_model",
    "drive_status",
    "inspect_files",
    "list_models",
    "model_to_dict",
    "normalize_slug",
    "scan_models",
]


