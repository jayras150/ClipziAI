"""
Admin API - pool proxy YouTube (upload banyak file, filter aktif, active.txt).

Lihat `app/services/proxy_pool.py` untuk alur lengkapnya.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import proxy_pool
from app.services.proxy_parser import mask_url, parse_proxy_text

router = APIRouter(dependencies=[Depends(get_current_admin)])
MAX_FILE_MB = 4


class ProxyTextIn(BaseModel):
    text: str = ""


class ProxyItemsIn(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)


class FilterIn(BaseModel):
    text: Optional[str] = None
    items: Optional[List[Dict[str, Any]]] = None
    target: str = proxy_pool.DEFAULT_TARGET
    timeout_s: float = Field(default=8.0, ge=2.0, le=60.0)
    concurrency: int = Field(default=25, ge=1, le=50)
    check_youtube: bool = True


class ToggleIn(BaseModel):
    enabled: Optional[bool] = None
    auto_use: Optional[bool] = None


class ItemDeleteIn(BaseModel):
    url: str


def _public_view(pool: Dict[str, Any]) -> Dict[str, Any]:
    """Tampilan aman: kredensial proxy dimask."""
    items = [
        {
            **item,
            "url": mask_url(item["url"]),
            "has_credentials": "@" in item["url"],
        }
        for item in pool.get("items", [])
    ]
    return {
        "enabled": pool.get("enabled"),
        "auto_use": pool.get("auto_use"),
        "rotation": pool.get("rotation"),
        "filter": pool.get("filter"),
        "updated_at": pool.get("updated_at"),
        "items": items,
        "active_count": len([i for i in pool.get("items", []) if i.get("status") == "active"]),
        "active_txt_lines": len([ln for ln in (pool.get("active_txt") or "").splitlines() if ln]),
        "active_txt_bytes": len(pool.get("active_txt") or ""),
    }


async def _audit(db, request, admin, action: str, meta: Optional[dict] = None) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="proxy_pool",
            resource_id="youtube",
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()


@router.get("")
async def read_pool(db: AsyncSession = Depends(get_db_session)):
    pool = await proxy_pool.get_pool(db)
    return _public_view(pool)


@router.post("/parse")
async def parse_text(payload: ProxyTextIn):
    """Preview normalisasi (tidak menyimpan)."""
    result = parse_proxy_text(payload.text)
    return {**result, "preview": [mask_url(i["url"]) for i in result["items"][:20]]}


@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload BANYAK file .txt/.csv proxy -> digabung, dinormalkan, di-dedupe."""
    combined: List[str] = []
    per_file: List[dict] = []
    for upload in files:
        raw = await upload.read()
        if len(raw) > MAX_FILE_MB * 1024 * 1024:
            per_file.append({"name": upload.filename, "valid": 0, "error": "file > 4 MB"})
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="ignore")
        combined.append(text)
        parsed = parse_proxy_text(text)
        per_file.append(
            {
                "name": upload.filename,
                "valid": parsed["valid"],
                "duplicate": parsed["duplicate"],
                "errors": len(parsed["errors"]),
            }
        )

    merged = parse_proxy_text("\n".join(combined))
    return {
        **merged,
        "files": per_file,
        "preview": [mask_url(i["url"]) for i in merged["items"][:20]],
    }


@router.put("")
async def save_pool(
    payload: ProxyItemsIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    pool = await proxy_pool.set_pool(db, {"items": payload.items})
    await _audit(db, request, current_admin, "proxy_pool_saved", {"items": len(pool["items"])})
    return _public_view(pool)


@router.post("/filter")
async def start_filter(
    payload: FilterIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """START FILTER ACTIVE PROXY: uji semua, simpan hanya yang aktif."""
    result = await proxy_pool.start_filter(
        raw_text=payload.text,
        items=payload.items,
        target=payload.target,
        timeout=payload.timeout_s,
        concurrency=payload.concurrency,
        check_youtube=payload.check_youtube,
        db=db,
    )
    if result.get("started"):
        await _audit(db, request, current_admin, "proxy_filter_started", {"total": result.get("total")})
    return result


@router.get("/filter/status")
async def filter_status():
    return proxy_pool.job_status()


@router.get("/active.txt", response_class=PlainTextResponse)
async def download_active(db: AsyncSession = Depends(get_db_session)):
    """File proxy aktif (kanonik) yang otomatis dipakai sistem."""
    pool = await proxy_pool.get_pool(db)
    return PlainTextResponse(
        pool.get("active_txt") or "",
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="active-proxies.txt"'},
    )


@router.delete("")
async def clear_pool(
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    pool = await proxy_pool.set_pool(db, {"items": []})
    await _audit(db, request, current_admin, "proxy_pool_cleared")
    return _public_view(pool)


@router.post("/delete")
async def delete_item(
    payload: ItemDeleteIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    pool = await proxy_pool.get_pool(db)
    items = [item for item in pool["items"] if item["url"] != payload.url]
    pool = await proxy_pool.set_pool(db, {"items": items})
    await _audit(db, request, current_admin, "proxy_pool_item_deleted")
    return _public_view(pool)


@router.put("/toggle")
async def toggle(
    payload: ToggleIn,
    db: AsyncSession = Depends(get_db_session),
):
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    pool = await proxy_pool.set_pool(db, changes)
    return _public_view(pool)
