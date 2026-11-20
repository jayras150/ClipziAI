"""Admin API - panel operasional Vast.ai (config, env, template, billing, logs)."""
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


class TemplateCreateIn(BaseModel):
    """Opsi pembuatan template worker (default = nilai konfigurasi yang aktif)."""

    name: Optional[str] = None
    image: Optional[str] = None
    disk_space: Optional[int] = None
    # Env pipeline ikut dibekukan di template (CLIPZI_TASK_ID tetap per task).
    include_env: bool = True
    sync_env_vars: bool = True
    public: bool = False
    activate: bool = True
    # Sekali klik dari admin dashboard: nama template baru otomatis
    # (clipzi-worker-1, -2, ...) dan image di-pin ke digest build terbaru.
    auto_name: bool = True
    pin_digest: bool = True


class TemplateSyncIn(BaseModel):
    """Sync satu template worker (env otomatis mengikuti provider model aktif)."""

    name: Optional[str] = None
    image: Optional[str] = None
    disk_space: Optional[int] = None
    public: bool = False
    activate: bool = True
    adopt_hash: Optional[str] = None


class ProviderTemplateIn(BaseModel):
    """Template per provider model (Clipzy Gdrive / Dropbox / …)."""

    provider: str = "gdrive"
    name: Optional[str] = None
    activate: bool = True


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


@router.post("/env/refresh")
async def refresh_worker_env(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Muat ulang kredensial dari database lalu kembalikan env terbaru.

    `settings` dihidrasi saat startup; kalau admin mengubah cookies/HF token/
    storage di tab lain, panel ini bisa menampilkan nilai lama sampai container
    di-restart. Endpoint ini menyamakan tampilan dengan isi database tanpa
    restart.
    """
    from app.services.runtime_credentials import hydrate_runtime_credentials

    summary = await hydrate_runtime_credentials()
    items = vast_admin.worker_env_spec()
    _audit(db, request, current_admin, "vast_env_refreshed", {"summary": summary})
    await db.commit()
    return {"items": items, "summary": summary}


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


@router.get("/template")
async def read_worker_template(db: AsyncSession = Depends(get_db_session)):
    """Status template worker + deteksi drift env (satu template untuk semua model)."""
    return await vast_admin.worker_template_status(db)


@router.post("/template/create")
async def create_worker_template(
    payload: TemplateCreateIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Buat template worker (image + env pipeline) lalu aktifkan untuk dispatch.

    Alias lama dari `/template/sync`; env tetap memakai build_worker_env()
    sehingga otomatis mengikuti provider/model aktif.
    """
    try:
        result = await vast_admin.create_worker_template(
            name=payload.name,
            image=payload.image,
            disk_space=payload.disk_space,
            include_env=payload.include_env,
            sync_env_vars=payload.sync_env_vars,
            public=payload.public,
            auto_name=payload.auto_name,
            pin_digest=payload.pin_digest,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if payload.activate and result.get("template_hash"):
        try:
            await vast_config.save_vast_config(
                db,
                {
                    "template_hash": result["template_hash"],
                    "worker_image": result["image"],
                    "worker_disk": result["disk_space"],
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result["activated"] = True
    else:
        result["activated"] = False

    if result.get("template_hash"):
        await vast_admin.save_template_meta(
            db,
            template_hash=result.get("template_hash"),
            name=result.get("name"),
            image=result.get("image"),
            disk=result.get("disk_space"),
            env_fingerprint=vast_admin.env_fingerprint(vast_admin.build_worker_env()),
            env_count=len(vast_admin.build_worker_env()),
        )

    _audit(
        db,
        request,
        current_admin,
        "vast_template_created",
        {
            "name": result.get("name"),
            "template_hash": result.get("template_hash"),
            "env_count": result.get("env_count"),
            "activated": result.get("activated"),
        },
    )
    await db.commit()
    return result


@router.post("/template/sync")
async def sync_worker_template(
    payload: TemplateSyncIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Buat/update template worker tunggal lalu aktifkan untuk dispatch.

    Env template berasal dari build_worker_env() sehingga otomatis memuat env
    provider/model yang sedang aktif (Gdrive/Dropbox/B2/HF/S3).
    """
    try:
        result = await vast_admin.sync_active_template(
            db,
            name=payload.name,
            image=payload.image,
            disk_space=payload.disk_space,
            public=payload.public,
            activate=payload.activate,
            adopt_hash=payload.adopt_hash,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _audit(
        db,
        request,
        current_admin,
        "vast_template_synced",
        {
            "name": result.get("name"),
            "template_hash": result.get("template_hash"),
            "env_count": result.get("env_count"),
            "activated": result.get("activated"),
            "adopted": result.get("adopted"),
        },
    )
    await db.commit()
    return result


@router.get("/templates")
async def read_provider_templates(db: AsyncSession = Depends(get_db_session)):
    """Daftar template Vast per provider model (Clipzy Gdrive/Dropbox/...)."""
    try:
        return await vast_admin.provider_templates(db)
    except Exception as exc:  # noqa: BLE001 - Vast belum dikonfigurasi
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from exc


@router.post("/templates/sync")
async def sync_provider_template(
    payload: ProviderTemplateIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Legacy: hanya MENGADOPSI hash template per-provider lama.

    Pembuatan template per provider sudah dihapus (satu template worker untuk
    semua model). Endpoint ini dipakai sekali untuk memigrasikan hash lama.
    """
    from app.services import model_sources

    try:
        provider = model_sources.get_provider(payload.provider)
    except model_sources.SourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    known = (await vast_admin.remembered_templates(db)).get(provider.id) or {}
    legacy_hash = str(known.get("template_hash") or "").strip()
    if not legacy_hash:
        raise HTTPException(
            status_code=400,
            detail=(
                "Template per-provider lama tidak ditemukan. Gunakan "
                "POST /api/admin/settings/vast/template/sync untuk satu template worker."
            ),
        )

    try:
        result = await vast_admin.sync_active_template(
            db,
            name=payload.name,
            activate=payload.activate,
            adopt_hash=legacy_hash,
            provider=provider.id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result["deprecated"] = True
    result["provider"] = provider.id
    _audit(
        db,
        request,
        current_admin,
        "vast_provider_template_adopted",
        {
            "provider": provider.id,
            "template_hash": result.get("template_hash"),
            "activated": result.get("activated"),
        },
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
