"""
Admin API - registry storage multi-provider (R2, B2, S3, Wasabi, dst).

Semua upload aplikasi (klip, thumbnail, SRT, branding, watermark) memakai satu
entry point `get_storage()` yang membaca konfigurasi ini: primary + mirror.
"""
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.core.security import encrypt_field
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import storage_registry as registry
from app.services.platform_settings import get_setting

router = APIRouter(dependencies=[Depends(get_current_admin)])


class StorageIn(BaseModel):
    id: Optional[str] = None
    name: str = Field(default="Storage", max_length=60)
    provider: str = "r2"
    bucket: str
    endpoint: str = ""
    region: str = "auto"
    path_style: Optional[bool] = None
    public_domain: str = ""
    path_prefix: str = ""
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    enabled: bool = True


class PrimaryIn(BaseModel):
    id: str


class MirrorsIn(BaseModel):
    ids: List[str] = Field(default_factory=list)


async def _load(db: AsyncSession) -> Dict[str, Any]:
    raw = await get_setting(db, registry.STORAGE_KEY, None)
    config = registry.normalize_config(raw if isinstance(raw, dict) else None)
    if not config["items"]:
        config = registry.set_config(registry._from_env())
    return config


async def _audit(db, request, admin, action: str, meta: Optional[dict] = None) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="storage",
            resource_id="registry",
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


@router.get("")
async def read_storage(db: AsyncSession = Depends(get_db_session)):
    config = await _load(db)
    registry.set_config(config)
    return registry.public_view(config)


@router.post("")
async def save_storage(
    payload: StorageIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    config = await _load(db)
    items = config["items"]
    existing = next((item for item in items if item["id"] == payload.id), None) if payload.id else None

    item = registry.normalize_item(
        {
            "id": (existing or {}).get("id") or payload.id or uuid4().hex[:12],
            "name": payload.name,
            "provider": payload.provider,
            "bucket": payload.bucket,
            "endpoint": payload.endpoint,
            "region": payload.region,
            "path_style": payload.path_style,
            "public_domain": payload.public_domain,
            "path_prefix": payload.path_prefix,
            "enabled": payload.enabled,
            "access_key_enc": (existing or {}).get("access_key_enc", ""),
            "secret_key_enc": (existing or {}).get("secret_key_enc", ""),
            "last_check": (existing or {}).get("last_check"),
        }
    )
    if payload.access_key:
        item["access_key_enc"] = encrypt_field(payload.access_key)
    if payload.secret_key:
        item["secret_key_enc"] = encrypt_field(payload.secret_key)

    if existing:
        items = [item if row["id"] == item["id"] else row for row in items]
    else:
        items.append(item)

    config["items"] = items
    if not config.get("primary_id"):
        config["primary_id"] = item["id"]

    saved = await registry.save_storage_config(db, config)
    await _audit(db, request, current_admin, "storage_saved", {"id": item["id"], "provider": item["provider"]})
    view = registry.public_view(saved)
    # Peringatan format kredensial (mis. B2 memakai keyID master yang terlalu pendek).
    try:
        access = payload.access_key or (
            __import__("app.core.security", fromlist=["decrypt_field"]).decrypt_field(item["access_key_enc"])
            if item.get("access_key_enc")
            else ""
        )
        secret = payload.secret_key or (
            __import__("app.core.security", fromlist=["decrypt_field"]).decrypt_field(item["secret_key_enc"])
            if item.get("secret_key_enc")
            else ""
        )
        view["warnings"] = registry.credential_warnings(item["provider"], access, secret)
    except Exception:
        view["warnings"] = []
    return view


@router.delete("/{item_id}")
async def delete_storage(
    item_id: str,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    config = await _load(db)
    items = [item for item in config["items"] if item["id"] != item_id]
    config["items"] = items
    config["mirror_ids"] = [mid for mid in config.get("mirror_ids", []) if mid != item_id]
    if config.get("primary_id") == item_id:
        config["primary_id"] = items[0]["id"] if items else None
    saved = await registry.save_storage_config(db, config)
    await _audit(db, request, current_admin, "storage_deleted", {"id": item_id})
    return registry.public_view(saved)


@router.post("/{item_id}/test")
async def test_storage(
    item_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    config = await _load(db)
    item = next((row for row in config["items"] if row["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Storage tidak ditemukan")

    result = registry.test_item(item)
    # Kalau berhasil hanya dengan path-style berbeda, simpan koreksinya otomatis.
    suggested = result.get("suggested") or {}
    if suggested.get("path_style") is not None:
        item["path_style"] = bool(suggested["path_style"])

    import datetime as _dt

    item["last_check"] = {
        **result,
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    saved = await registry.save_storage_config(db, config)
    return {"result": result, "storage": registry.public_view(saved)}


@router.put("/primary")
async def set_primary(
    payload: PrimaryIn,
    db: AsyncSession = Depends(get_db_session),
):
    config = await _load(db)
    if not any(item["id"] == payload.id for item in config["items"]):
        raise HTTPException(status_code=404, detail="Storage tidak ditemukan")
    config["primary_id"] = payload.id
    config["mirror_ids"] = [mid for mid in config.get("mirror_ids", []) if mid != payload.id]
    saved = await registry.save_storage_config(db, config)
    return registry.public_view(saved)


@router.put("/mirrors")
async def set_mirrors(
    payload: MirrorsIn,
    db: AsyncSession = Depends(get_db_session),
):
    config = await _load(db)
    valid = {item["id"] for item in config["items"]}
    config["mirror_ids"] = [mid for mid in payload.ids if mid in valid and mid != config.get("primary_id")]
    saved = await registry.save_storage_config(db, config)
    return registry.public_view(saved)


class DomainIn(BaseModel):
    domain: str = Field(default="", max_length=200)
    item_id: Optional[str] = None


@router.post("/domain-check")
async def domain_check(payload: DomainIn, db: AsyncSession = Depends(get_db_session)):
    """Uji custom domain: DNS + HTTPS + sertifikat (CNAME dipasang manual)."""
    config = await _load(db)
    item = None
    if payload.item_id:
        item = next((row for row in config["items"] if row["id"] == payload.item_id), None)
    if item is None:
        item = next(
            (row for row in config["items"] if row.get("provider") == "r2"), None
        )
    if item is None:
        raise HTTPException(status_code=404, detail="Belum ada storage R2 untuk dipasangi domain")
    return {"result": registry.check_custom_domain(payload.domain, item), "storage_id": item["id"]}


@router.post("/{item_id}/custom-domain")
async def set_custom_domain(
    item_id: str,
    payload: DomainIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Simpan custom domain sebagai `public_domain` storage + audit."""
    config = await _load(db)
    item = next((row for row in config["items"] if row["id"] == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Storage tidak ditemukan")

    domain = registry.normalize_domain(payload.domain)
    check = registry.check_custom_domain(domain, item) if domain else {"domain": ""}
    item["public_domain"] = ("https://" + domain) if domain else ""
    item["last_domain_check"] = {
        **check,
        "at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    registry._public_cache.clear()
    saved = await registry.save_storage_config(db, config)
    await _audit(
        db, request, current_admin, "storage_custom_domain", {"id": item_id, "domain": domain}
    )
    return {"storage": registry.public_view(saved), "result": item["last_domain_check"]}

class SyncIn(BaseModel):
    mode: str = Field(default="push", description="push | reconcile | heal")
    limit: int = Field(default=50, ge=1, le=500)
    max_size_mb: int = Field(default=500, ge=1, le=10000)


@router.post("/sync")
async def sync_storage(
    payload: Optional[SyncIn] = None,
    request: Request = None,  # type: ignore[assignment]
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Mulai sync di background (tidak menahan request → tidak timeout)."""
    from app.services import storage_sync

    body = payload or SyncIn()
    await _load(db)  # pastikan config terbaru terpasang
    result = storage_sync.start_sync(
        mode=body.mode, limit=body.limit, max_size_mb=body.max_size_mb
    )
    if result.get("started") and request is not None:
        await _audit(
            db,
            request,
            current_admin,
            "storage_sync_started",
            {"mode": body.mode, "limit": body.limit, "max_size_mb": body.max_size_mb},
        )
    return result


@router.get("/sync/status")
async def sync_status():
    from app.services import storage_sync

    return storage_sync.job_status()


@router.post("/sync/cancel")
async def sync_cancel():
    from app.services import storage_sync

    return storage_sync.cancel_sync()


@router.post("/heal")
async def heal_storage(
    payload: Optional[SyncIn] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Pulihkan objek yang hilang di primary dari mirror."""
    from app.services import storage_sync

    body = payload or SyncIn()
    await _load(db)
    return storage_sync.start_sync(
        mode="heal", limit=body.limit, max_size_mb=body.max_size_mb
    )


@router.get("/locate")
async def locate_object(key: str, db: AsyncSession = Depends(get_db_session)):
    """Cari satu objek di semua provider (primary + mirror)."""
    from app.services import storage_sync

    if not key.strip():
        raise HTTPException(status_code=400, detail="Query 'key' wajib diisi")
    await _load(db)
    return storage_sync.locate(key)

