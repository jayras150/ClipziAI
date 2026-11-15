"""Admin API - panel operasional Vast.ai (config, env, billing, logs)."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import vast_admin, vast_config

router = APIRouter(dependencies=[Depends(get_current_admin)])


class EnvSyncIn(BaseModel):
    keys: Optional[List[str]] = None
    dry_run: bool = False


def _audit(
    db: AsyncSession,
    request: Request,
    admin: User,
    action: str,
    meta: Optional[dict] = None,
) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="vast",
            resource_id=None,
            meta_data=meta or {},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("")
async def read_vast_config(db: AsyncSession = Depends(get_db_session)):
    cfg = await vast_config.get_vast_config(db)
    return vast_config.public_vast_config(cfg)


@router.put("")
async def update_vast_config(
    payload: Dict[str, Any],
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        cfg = await vast_config.save_vast_config(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(
        db,
        request,
        current_admin,
        "vast_settings_updated",
        {"fields": sorted(key for key in payload if key not in ("api_key",))},
    )
    await db.commit()
    return vast_config.public_vast_config(cfg)


@router.post("/reset")
async def reset_vast_config(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    cfg = await vast_config.reset_vast_config(db)
    _audit(db, request, current_admin, "vast_settings_reset")
    await db.commit()
    return vast_config.public_vast_config(cfg)


@router.get("/connections")
async def vast_connections():
    """Daftar Cloud Sync + status ID restore yang sedang dipakai."""
    try:
        return await vast_admin.detect_connection()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/connections/auto")
async def vast_connection_auto(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Pilih otomatis koneksi yang valid lalu simpan ke konfigurasi restore."""
    try:
        result = await vast_admin.detect_connection()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not result.get("selected"):
        raise HTTPException(
            status_code=409,
            detail=str(result.get("error") or "Tidak ada koneksi yang bisa dipilih otomatis."),
        )
    cfg = await vast_config.save_vast_config(
        db, {"restore_connection": result["selected"]}
    )
    _audit(
        db,
        request,
        current_admin,
        "vast_restore_connection_auto",
        {
            "configured": result.get("configured"),
            "selected": result.get("selected"),
        },
    )
    await db.commit()
    return {
        **result,
        "config": vast_config.public_vast_config(cfg),
    }


@router.post("/test")
async def test_vast_connection(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await vast_admin.test_connection()
    _audit(
        db,
        request,
        current_admin,
        "vast_connection_tested",
        {"ok": bool(result.get("ok"))},
    )
    await db.commit()
    return result


@router.post("/offers")
async def test_vast_offers(
    limit: int = 5,
    current_admin: User = Depends(get_current_admin),
):
    try:
        return await vast_admin.test_offers(limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/env")
async def read_worker_env():
    return {"items": vast_admin.worker_env_spec()}


@router.get("/env/export", response_class=PlainTextResponse)
async def export_worker_env(
    request: Request,
    reveal: bool = False,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Unduh .env worker. `reveal=true` menampilkan nilai asli (admin, diaudit)."""
    text = vast_admin.env_text(reveal=reveal)
    if reveal:
        _audit(
            db,
            request,
            current_admin,
            "vast_env_exported_revealed",
            {"keys": len(vast_admin.worker_env_spec())},
        )
        await db.commit()
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@router.get("/env/text")
async def export_worker_env_json(
    request: Request,
    reveal: bool = False,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Versi JSON dari export .env (untuk tombol Copy/Download di admin)."""
    text = vast_admin.env_text(reveal=reveal)
    if reveal:
        _audit(
            db,
            request,
            current_admin,
            "vast_env_exported_revealed",
            {"keys": len(vast_admin.worker_env_spec())},
        )
        await db.commit()
    return {"text": text, "reveal": reveal}


@router.post("/env/sync")
async def sync_worker_env(
    payload: EnvSyncIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        result = await vast_admin.sync_env_to_vast(
            keys=payload.keys, dry_run=payload.dry_run
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not payload.dry_run:
        _audit(
            db,
            request,
            current_admin,
            "vast_env_synced",
            {"summary": result.get("summary")},
        )
        await db.commit()
    return result


@router.get("/billing")
async def read_vast_billing(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    invoice_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
):
    try:
        return await vast_admin.billing_summary(
            db,
            start_date=start_date,
            end_date=end_date,
            invoice_type=invoice_type,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
