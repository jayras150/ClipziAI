"""Setelan AI versi admin: simpan, uji koneksi, injeksi ke environment."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services.ai_client import PROVIDER_DEFAULTS
from app.services.ai_config import (
    ai_is_configured,
    apply_ai_config_to_env,
    effective_base_url,
    get_ai_config,
    public_ai_config,
    set_ai_config,
    decrypt_api_key,
)

router = APIRouter()


class AIConfigIn(BaseModel):
    enabled: bool = True
    provider: str = "openrouter"
    base_url: str = ""
    api_key: Optional[str] = None
    clear_api_key: bool = False
    model_metadata: str = "openai/gpt-4o-mini"
    model_rerank: str = "openai/gpt-4o-mini"
    model_regenerate: str = "openai/gpt-6-luna"
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    max_tokens: int = Field(default=2048, ge=128, le=8192)
    timeout_seconds: int = Field(default=90, ge=10, le=300)
    max_retries: int = Field(default=1, ge=0, le=3)
    rerank_enabled: bool = True
    metadata_enabled: bool = True
    rerank_budget_seconds: int = Field(default=120, ge=20, le=600)
    metadata_budget_seconds: int = Field(default=180, ge=20, le=900)


@router.get("/ai")
async def read_ai(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    cfg = await get_ai_config(db)
    return public_ai_config(cfg)


@router.put("/ai")
async def update_ai(
    payload: AIConfigIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    before = public_ai_config(await get_ai_config(db))
    data = payload.model_dump()
    cfg = await set_ai_config(db, data)
    after = public_ai_config(cfg)
    injection = apply_ai_config_to_env(cfg)

    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="platform_ai_updated",
            resource_type="platform_setting",
            resource_id="ai",
            old_values=before,
            new_values=after,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    after["injected"] = injection["injected"]
    return after


@router.post("/ai/test")
async def test_ai(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Panggil provider dengan prompt mini untuk memastikan kredensial hidup."""
    import time

    from openai import AsyncOpenAI

    cfg = await get_ai_config(db)
    if not ai_is_configured(cfg):
        raise HTTPException(status_code=400, detail="AI belum aktif atau API key kosong.")

    client = AsyncOpenAI(
        api_key=decrypt_api_key(cfg.get("api_key_enc")) or "sk-no-key-provided",
        base_url=effective_base_url(cfg),
        timeout=float(cfg["timeout_seconds"]),
        max_retries=0,
    )
    started = time.monotonic()
    try:
        response = await client.chat.completions.create(
            model=cfg["model_metadata"],
            messages=[
                {"role": "system", "content": "Balas hanya satu objek JSON."},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=16,
            temperature=0,
        )
        answer = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        return {
            "ok": False,
            "provider": cfg["provider"],
            "model": cfg["model_metadata"],
            "base_url": effective_base_url(cfg),
            "error": (type(exc).__name__ + ": " + str(exc))[:300],
        }
    latency_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": bool(answer),
        "provider": cfg["provider"],
        "model": cfg["model_metadata"],
        "base_url": effective_base_url(cfg),
        "latency_ms": latency_ms,
        "sample": answer[:120],
    }
