"""Admin API - dynamic Whisper model registry (Google Drive)."""
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import whisper_model_manager as manager
from app.services.drive_service import DriveError

router = APIRouter(dependencies=[Depends(get_current_admin)])


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


@router.get("")
async def read_models(db: AsyncSession = Depends(get_db_session)):
    rows = await manager.list_models(db)
    status = await manager.drive_status()
    active = next((manager.model_to_dict(row) for row in rows if row.is_active), None)
    return {
        **status,
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
