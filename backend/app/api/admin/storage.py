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
    return registry.public_view(saved)


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


@router.post("/sync")
async def sync_storage(limit: int = 200):
    """Salin objek yang belum ada di mirror (manual, dari dashboard)."""
    result = await registry.sync_mirrors(limit=limit)
    return result
