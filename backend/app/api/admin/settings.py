"""
Setelan platform versi admin (Batch B): watermark.

Semua endpoint di sini WAJIB token admin (cookie HttpOnly / Bearer) â€” lihat
`app/api/admin/deps.py`. Setiap perubahan dicatat ke `audit_logs`.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services.platform_settings import (
    PLANS,
    POSITIONS,
    get_watermark_config,
    normalize_watermark,
    set_watermark_config,
)

router = APIRouter()


class WatermarkConfigIn(BaseModel):
    enabled: bool = False
    plans: List[str] = Field(default_factory=lambda: ["free"])
    image_url: Optional[str] = None
    text: Optional[str] = Field(default=None, max_length=60)
    position: str = "bottom-right"
    opacity: float = 0.85
    scale: float = 0.18
    text_color: str = "#ffffff"
    margin: int = 40

    @field_validator("plans")
    @classmethod
    def _validate_plans(cls, value: List[str]) -> List[str]:
        cleaned = [str(p).lower() for p in value if str(p).lower() in PLANS]
        if not cleaned:
            raise ValueError(f"plans harus berisi salah satu dari {list(PLANS)}")
        return cleaned

    @field_validator("position")
    @classmethod
    def _validate_position(cls, value: str) -> str:
        if value not in POSITIONS:
            raise ValueError(f"position harus salah satu dari {list(POSITIONS)}")
        return value


def _require_manager(admin: User) -> None:
    """Semua email di ADMIN_EMAILS boleh mengubah branding platform."""
    return None


@router.get("/watermark")
async def read_watermark(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    return await get_watermark_config(db)


@router.put("/watermark")
async def update_watermark(
    payload: WatermarkConfigIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    _require_manager(current_admin)
    if not payload.image_url and not payload.text:
        raise HTTPException(
            status_code=400, detail="Isi image_url atau text sebagai watermark"
        )

    before = await get_watermark_config(db)
    after = await set_watermark_config(db, payload.model_dump())

    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_watermark_updated",
            resource_type="platform_setting",
            resource_id="watermark",
            old_values=before,
            new_values=after,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    return after


@router.post("/watermark/reset")
async def reset_watermark(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    _require_manager(current_admin)
    return await set_watermark_config(db, normalize_watermark(None))
