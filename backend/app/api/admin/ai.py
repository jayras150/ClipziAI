"""Setelan AI versi admin: simpan, uji koneksi, injeksi ke environment."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services.ai_client import PROVIDER_DEFAULTS, provider_metadata
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


class AIModelsIn(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None


# Cache daftar model: 5 menit. Katalog provider jarang berubah, sedangkan
# dashboard bisa memanggil endpoint ini berkali-kali saat user memilih model.
_MODEL_CACHE: Dict[str, tuple[float, List[dict]]] = {}
_MODEL_CACHE_TTL = 300


@router.get("/ai/providers")
async def list_ai_providers(current_admin: User = Depends(get_current_admin)):
    """Metadata provider (label, base URL bawaan, model default, link API key)."""
    return {"items": provider_metadata()}


@router.post("/ai/models")
async def list_ai_models(
    payload: AIModelsIn,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Ambil daftar model langsung dari provider (`GET {base_url}/models`).

    Dipakai dashboard supaya admin memilih model dari daftar nyata (dengan
    pencarian) alih-alih mengetik manual. Bila provider tidak menyediakan
    /models, admin tetap bisa mengisi nama model manual.
    """
    import time

    import httpx

    cfg = await get_ai_config(db)
    provider = (payload.provider or cfg.get("provider") or "custom").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])

    if payload.base_url and payload.base_url.strip():
        base_url = payload.base_url.strip()
    elif provider == (cfg.get("provider") or "").strip().lower():
        base_url = effective_base_url(cfg) or defaults.get("base_url") or ""
    else:
        base_url = defaults.get("base_url") or ""

    if not base_url:
        raise HTTPException(
            status_code=400,
            detail="Provider ini butuh Base URL. Isi Base URL lalu muat ulang daftar model.",
        )

    api_key = (payload.api_key or "").strip() or decrypt_api_key(cfg.get("api_key_enc")) or ""
    if not api_key and provider not in ("ollama", "vllm", "custom"):
        raise HTTPException(
            status_code=400,
            detail="API key belum ada. Simpan API key dulu, lalu muat ulang daftar model.",
        )

    cache_key = f"{provider}|{base_url.rstrip('/')}"
    cached = _MODEL_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _MODEL_CACHE_TTL:
        return {
            "provider": provider,
            "base_url": base_url,
            "cached": True,
            "count": len(cached[1]),
            "models": cached[1],
        }

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gagal menghubungi {url}: {type(exc).__name__}: {str(exc)[:160]}",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"{url} -> {response.status_code}: {response.text[:200]}",
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Respons provider bukan JSON.")

    raw_items = data.get("data") if isinstance(data, dict) else None
    if raw_items is None and isinstance(data, dict):
        raw_items = data.get("models")
    if not isinstance(raw_items, list):
        raise HTTPException(status_code=502, detail="Provider tidak mengembalikan daftar model.")

    models: List[dict] = []
    for item in raw_items:
        if isinstance(item, str):
            models.append({"id": item, "owned_by": None, "context_length": None})
            continue
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name") or item.get("model")
        if not model_id:
            continue
        models.append(
            {
                "id": str(model_id),
                "owned_by": item.get("owned_by") or item.get("organization") or None,
                "context_length": item.get("context_length") or item.get("context_window"),
                "pricing": item.get("pricing"),
            }
        )

    models.sort(key=lambda entry: entry["id"].lower())
    _MODEL_CACHE[cache_key] = (time.time(), models)
    return {
        "provider": provider,
        "base_url": base_url,
        "cached": False,
        "count": len(models),
        "models": models,
    }


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
                {"role": "system", "content": "Balas satu kata: pong."},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=64,
            temperature=0,
        )
        choice = response.choices[0]
        answer = (choice.message.content or "").strip()
        finish = getattr(choice, "finish_reason", None)
        usage = getattr(response, "usage", None)
        usage_data = (
            usage.model_dump()
            if usage is not None and hasattr(usage, "model_dump")
            else None
        )
    except Exception as exc:
        return {
            "ok": False,
            "provider": cfg["provider"],
            "model": cfg["model_metadata"],
            "base_url": effective_base_url(cfg),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": (type(exc).__name__ + ": " + str(exc))[:300],
        }
    latency_ms = int((time.monotonic() - started) * 1000)
    return {
        "ok": True,
        "provider": cfg["provider"],
        "model": cfg["model_metadata"],
        "base_url": effective_base_url(cfg),
        "latency_ms": latency_ms,
        "sample": answer[:120],
        "finish_reason": finish,
        "usage": usage_data,
    }
