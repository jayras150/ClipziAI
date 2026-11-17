"""Admin API - dynamic Whisper model registry (Google Drive)."""
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import (
    model_sources,
    platform_settings as ps,
    vast_admin,
    vast_config,
    whisper_model_manager as manager,
)
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


class SourceSaveIn(BaseModel):
    provider: str = "gdrive"
    values: Dict[str, Any] = {}
    auto_template: bool = True
    activate: bool = True
    reset: bool = False


class SourceTestIn(BaseModel):
    provider: Optional[str] = None
    values: Dict[str, Any] = {}


class SourceTemplateIn(BaseModel):
    provider: Optional[str] = None
    activate: bool = True



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
async def download_colab_notebook(provider: str = "gdrive"):
    """Template notebook Colab untuk provider terpilih (default Google Drive)."""
    try:
        path = model_sources.notebook_path(provider)
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    content = path.read_text(encoding="utf-8")
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Template notebook bukan JSON valid.") from exc
    provider_meta = model_sources.get_provider(provider)
    return {
        "filename": f"clipzi-whisper-{provider_meta.id}.ipynb",
        "provider": provider_meta.id,
        "content": content,
    }


@router.get("")
async def read_models(db: AsyncSession = Depends(get_db_session)):
    rows = await manager.list_models(db)
    status = await manager.drive_status()
    colab = await _colab_config(db)
    active = next((manager.model_to_dict(row) for row in rows if row.is_active), None)
    try:
        source = await manager.source_status(db)
    except Exception as exc:  # noqa: BLE001 - jangan gagalkan halaman model
        source = {"error": str(exc)[:300]}
    return {
        **status,
        **colab,
        "source": source,
        "active_model_id": active["id"] if active else None,
        "active_model": active,
        "items": [manager.model_to_dict(row) for row in rows],
    }


@router.get("/source")
async def read_source(db: AsyncSession = Depends(get_db_session)):
    """Provider aktif + manifest lengkap (untuk tombol provider di admin)."""
    try:
        source = await model_sources.get_source(db)
        view = model_sources.public_view(source["provider"])
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    templates: Dict[str, Any] = {"items": [], "active_hash": ""}
    try:
        templates = await vast_admin.provider_templates(db)
    except Exception as exc:  # noqa: BLE001 - Vast belum dikonfigurasi
        templates["error"] = str(exc)[:300]
    return {
        **source,
        "providers": view["providers"],
        "warnings": view["warnings"],
        "templates": templates,
    }


@router.put("/source")
async def save_source(
    payload: SourceSaveIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Simpan provider + kredensial, lalu buat/aktifkan template Vast-nya."""
    try:
        provider = model_sources.get_provider(payload.provider)
        saved = await model_sources.save_source(
            db,
            provider.id,
            payload.values,
            provider=provider,
            reset=payload.reset,
        )
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Satu template worker untuk semua provider; env otomatis mengikuti model aktif.
    template: Dict[str, Any] = {"skipped": True}
    if payload.auto_template:
        try:
            template = await vast_admin.sync_active_template(
                db,
                activate=payload.activate,
                provider=provider.id,
            )
            template["skipped"] = False
        except (ValueError, RuntimeError) as exc:
            template = {"skipped": False, "error": str(exc)[:400]}
    _audit(
        db,
        request,
        current_admin,
        "whisper_source_saved",
        meta={
            "provider": provider.id,
            "template_name": provider.template_name,
            "template_action": template.get("action"),
            "template_hash": template.get("template_hash"),
        },
    )
    await db.commit()
    return {"ok": True, "source": saved, "template": template}


@router.post("/source/test")
async def test_source(
    payload: SourceTestIn,
    db: AsyncSession = Depends(get_db_session),
):
    try:
        return await model_sources.test_source(db, payload.provider, payload.values)
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/source/template")
async def sync_source_template(
    payload: SourceTemplateIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Legacy alias: sekarang menyegarkan SATU template worker."""
    try:
        source = await model_sources.get_source(db)
        provider = model_sources.get_provider(payload.provider or source["provider"])
        template = await vast_admin.sync_active_template(
            db, activate=payload.activate, provider=provider.id
        )
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _audit(
        db,
        request,
        current_admin,
        "vast_template_synced",
        {
            "provider": provider.id,
            "name": template.get("name"),
            "template_hash": template.get("template_hash"),
            "activated": template.get("activated"),
            "via": "whisper-source",
        },
    )
    await db.commit()
    template["deprecated"] = True
    return template


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
        meta={
            "slug": payload["slug"],
            "provider": payload.get("provider"),
            "remote_path": payload.get("remote_path"),
        },
    )
    await db.commit()
    restore_env = model_sources.restore_env()
    provider = model_sources.get_provider(payload.get("provider"))
    template_sync: Dict[str, Any] = {}
    try:
        cfg = await vast_config.get_vast_config(db)
        if str(cfg.get("worker_image") or "").strip() and str(cfg.get("api_key_enc") or ""):
            template_sync = await vast_admin.sync_active_template(
                db, activate=True, provider=provider.id
            )
    except Exception as exc:  # noqa: BLE001 - aktivasi model tetap sukses
        template_sync = {"error": str(exc)[:300]}
    return {
        "ok": True,
        "model": payload,
        "template_sync": template_sync,
        "provider": provider.id,
        "provider_label": provider.label,
        "restore_mode": provider.restore_mode,
        "restore_src": restore_env.get("CLIPZI_MODEL_URL")
        or restore_env.get("CLIPZI_HF_REPO")
        or payload.get("remote_path"),
        "restore_env": sorted(restore_env),
        "restore_model_path": model_sources.MODEL_WORKSPACE,
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
