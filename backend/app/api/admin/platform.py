"""
Setelan ekosistem (Settings -> Platform) + permintaan ganti domain 1 klik.

Lihat `app/services/platform_config.py` untuk alur lengkap dan alasannya.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import platform_config as pc

router = APIRouter(dependencies=[Depends(get_current_admin)])


class PlatformIn(BaseModel):
    site_url: Optional[str] = None
    admin_url: Optional[str] = None
    support_email: Optional[str] = None
    timezone: Optional[str] = None
    maintenance_mode: Optional[bool] = None
    signup_enabled: Optional[bool] = None
    google_client_id: Optional[str] = None


class DomainApplyIn(BaseModel):
    domain: str = Field(description="Domain publik baru, mis. clipzy.id")
    admin_domain: Optional[str] = Field(
        default=None, description="Subdomain admin, mis. admin.clipzy.id"
    )
    update_dns: bool = Field(
        default=True, description="Minta agent memperbarui DNS Cloudflare (bila token tersedia)"
    )


def _agent_steps(domain: str, admin_domain: str) -> list[str]:
    steps = [
        f"DNS: A record '{domain}' -> IP VPS (proxied/Cloudflare).",
        f"Cloudflare Access: policy email admin untuk '{admin_domain or domain}'.",
        "Agent VPS menulis DOMAIN/ADMIN_DOMAIN ke .env lalu reload Caddy.",
        "Update OAuth redirect URI (Google/YouTube) ke domain baru bila dipakai.",
    ]
    if admin_domain:
        steps.insert(1, f"DNS: A record '{admin_domain}' -> IP VPS (proxied).")
    return steps


@router.get("/platform")
async def read_platform(db: AsyncSession = Depends(get_db_session)):
    config = await pc.get_platform_config(db)
    return {
        **config,
        "effective_site_url": pc.site_url(config),
        "agent_hint": "deploy/clipzi-domain-sync.sh + clipzi-domain-sync.timer (30 detik)",
    }


@router.put("/platform")
async def update_platform(
    payload: PlatformIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    before = await pc.get_platform_config(db)
    data: Dict[str, Any] = {}

    try:
        if payload.site_url is not None:
            data["site_url"] = pc.validate_url(payload.site_url, "Site URL")
        if payload.admin_url is not None:
            data["admin_url"] = pc.validate_url(payload.admin_url, "Admin URL")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if payload.support_email is not None:
        data["support_email"] = payload.support_email.strip()
    if payload.timezone is not None:
        data["timezone"] = payload.timezone.strip()
    if payload.maintenance_mode is not None:
        data["maintenance_mode"] = payload.maintenance_mode
    if payload.signup_enabled is not None:
        data["signup_enabled"] = payload.signup_enabled
    if payload.google_client_id is not None:
        data["google_client_id"] = payload.google_client_id.strip()

    config = await pc.set_platform_config(db, data)
    injection = pc.apply_platform_config_to_env(config)

    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_settings_updated",
            resource_type="platform_setting",
            resource_id="platform",
            old_values=before,
            new_values=config,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return {
        **config,
        "effective_site_url": pc.site_url(config),
        "injected": injection["injected"],
    }


@router.put("/platform/maintenance")
async def set_maintenance(
    enabled: bool,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Toggle cepat mode maintenance."""
    config = await pc.set_platform_config(db, {"maintenance_mode": enabled})
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_maintenance_toggled",
            resource_type="platform_setting",
            resource_id="platform",
            new_values={"maintenance_mode": enabled},
            ip_address=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return {"maintenance_mode": config["maintenance_mode"]}


@router.post("/platform/apply-domain")
async def apply_domain(
    payload: DomainApplyIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Tandai domain baru untuk diterapkan agent VPS (1 klik dari dashboard).

    Backend TIDAK mengubah server sendiri; ia menyimpan permintaan + status
    `pending`. Agent membaca DB tiap 30 detik, menerapkan, lalu melapor balik.
    """
    try:
        domain = pc.normalize_domain(payload.domain)
        admin_domain = pc.normalize_domain(payload.admin_domain or "")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not domain or "." not in domain:
        raise HTTPException(status_code=400, detail="Domain tidak valid.")

    config = await pc.set_platform_config(
        db,
        {
            "pending_domain": domain,
            "pending_admin_domain": admin_domain or None,
            "domain_status": "pending",
            "domain_requested_at": datetime.now(timezone.utc).isoformat(),
            "domain_last_error": None,
        },
    )

    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_domain_change_requested",
            resource_type="platform_setting",
            resource_id="platform",
            new_values={
                "domain": domain,
                "admin_domain": admin_domain or None,
                "update_dns": payload.update_dns,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()

    return {
        "status": "pending",
        "domain": domain,
        "admin_domain": admin_domain or None,
        "checklist": _agent_steps(domain, admin_domain),
        "message": (
            "Permintaan diterima. Agent di VPS akan menerapkan dalam ~30 detik "
            "(pastikan DNS sudah mengarah ke server ini)."
        ),
        "config": config,
    }


@router.get("/platform/domain-status")
async def domain_status(db: AsyncSession = Depends(get_db_session)):
    config = await pc.get_platform_config(db)
    return {
        "status": config.get("domain_status"),
        "pending_domain": config.get("pending_domain"),
        "pending_admin_domain": config.get("pending_admin_domain"),
        "applied_domain": config.get("applied_domain"),
        "requested_at": config.get("domain_requested_at"),
        "applied_at": config.get("domain_applied_at"),
        "last_error": config.get("domain_last_error"),
        "effective_site_url": pc.site_url(config),
    }


@router.post("/platform/domain-cancel")
async def cancel_domain(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Batalkan permintaan ganti domain yang masih pending."""
    config = await pc.set_platform_config(
        db,
        {
            "pending_domain": None,
            "pending_admin_domain": None,
            "domain_status": "idle",
            "domain_last_error": None,
        },
    )
    return {"status": config["domain_status"], "message": "Permintaan dibatalkan."}

