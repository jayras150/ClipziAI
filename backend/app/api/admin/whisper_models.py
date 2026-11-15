"""Admin API - dynamic Whisper model registry (Google Drive)."""
import json
import re
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import platform_settings as ps
from app.services import whisper_model_manager as manager
from app.services.drive_service import DriveError

router = APIRouter(dependencies=[Depends(get_current_admin)])

COLAB_SETTING_KEY = "whisper_colab"
COLAB_NOTEBOOK_PATH = (
    Path(__file__).resolve().parents[2] / "templates" / "whisper_colab.ipynb"
)
COLAB_FILENAME = "clipzi-whisper-colab.ipynb"
DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
DRIVE_FILE_URL_RE = re.compile(r"/file/d/([A-Za-z0-9_-]{10,})")
DRIVE_ID_QUERY_RE = re.compile(r"[?&]id=([A-Za-z0-9_-]{10,})")


class ColabNotebookIn(BaseModel):
    notebook_file_id: str = ""



def _audit(
    db: AsyncSession,
    request: Request,
    admin: User,
    action: str,
    model_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="whisper_model",
            resource_id=str(model_id) if model_id else None,
            meta_data=meta or {},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


def _extract_drive_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for pattern in (DRIVE_FILE_URL_RE, DRIVE_ID_QUERY_RE):
        match = pattern.search(text)
        if match:
            text = match.group(1)
            break
    if not DRIVE_ID_RE.fullmatch(text):
        raise HTTPException(
            status_code=400,
            detail=(
                "File ID notebook tidak valid. Tempel ID dari URL "
                "https://drive.google.com/file/d/<ID>/view"
            ),
        )
    return text


async def _colab_config(db: AsyncSession) -> dict:
    stored = await ps.get_setting(db, COLAB_SETTING_KEY, {})
    stored = stored if isinstance(stored, dict) else {}
    file_id = str(stored.get("notebook_file_id") or "").strip()
    if file_id and not DRIVE_ID_RE.fullmatch(file_id):
        file_id = ""
    from app.services.drive_service import DriveService

    drive = DriveService()
    folder_url = (
        f"https://drive.google.com/drive/folders/{drive.folder_id}"
        if drive.folder_id
        else ""
    )
    return {
        "notebook_file_id": file_id,
        "notebook_url": (
            f"https://colab.research.google.com/drive/{file_id}" if file_id else ""
        ),
        "folder_url": folder_url,
    }


@router.get("/colab")
async def read_colab_config(db: AsyncSession = Depends(get_db_session)):
    return await _colab_config(db)


@router.put("/colab")
async def save_colab_config(
    payload: ColabNotebookIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    file_id = _extract_drive_id(payload.notebook_file_id)
    await ps.set_setting(db, COLAB_SETTING_KEY, {"notebook_file_id": file_id})
    _audit(
        db,
        request,
        current_admin,
        "whisper_colab_updated",
        meta={"notebook_file_id_set": bool(file_id)},
    )
    await db.commit()
    return {"ok": True, **(await _colab_config(db))}


@router.get("/colab/notebook")
async def download_colab_notebook():
    if not COLAB_NOTEBOOK_PATH.is_file():
        raise HTTPException(status_code=500, detail="Template notebook tidak ditemukan.")
    content = COLAB_NOTEBOOK_PATH.read_text(encoding="utf-8")
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Template notebook bukan JSON valid.") from exc
    return {"filename": COLAB_FILENAME, "content": content}


@router.get("")
async def read_models(db: AsyncSession = Depends(get_db_session)):
    rows = await manager.list_models(db)
    status = await manager.drive_status()
    colab = await _colab_config(db)
    active = next((manager.model_to_dict(row) for row in rows if row.is_active), None)
    return {
        **status,
        **colab,
        "active_model_id": active["id"] if active else None,
        "active_model": active,
        "items": [manager.model_to_dict(row) for row in rows],
    }


@router.post("/scan")
async def scan_models(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await manager.scan_models(db)
    except DriveError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(
        db,
        request,
        current_admin,
        "whisper_models_scanned",
        meta={key: result.get(key) for key in ("created", "updated", "missing", "total")},
    )
    await db.commit()
    result.update(await manager.drive_status())
    return result


@router.post("/{model_id}/activate")
async def activate_model(
    model_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        row = await manager.activate_model(db, model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DriveError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    payload = manager.model_to_dict(row)
    _audit(
        db,
        request,
        current_admin,
        "whisper_model_activated",
        model_id=payload["id"],
        meta={"slug": payload["slug"], "drive_path": payload["drive_path"]},
    )
    await db.commit()
    return {
        "ok": True,
        "model": payload,
        "restore_src": payload["drive_path"],
        "restore_model_path": manager.MODEL_WORKSPACE,
    }


@router.delete("/{model_id}")
async def delete_model(
    model_id: UUID,
    request: Request,
    delete_drive: bool = False,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await manager.delete_model(
            db, model_id, delete_drive=delete_drive
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DriveError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _audit(
        db,
        request,
        current_admin,
        "whisper_model_deleted",
        model_id=str(model_id),
        meta={"delete_drive": delete_drive, **result},
    )
    await db.commit()
    return {"ok": True, **result}
