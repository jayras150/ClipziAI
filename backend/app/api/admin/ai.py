"""Setelan AI versi admin: simpan, uji koneksi, injeksi ke environment."""
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.user import User
from app.services import ai_prompts
from app.services.ai_client import PROVIDER_DEFAULTS, provider_metadata
from app.services.ai_config import (
    ai_is_configured,
    ai_status_hint,
    apply_ai_config_to_env,
    effective_base_url,
    get_ai_config,
    public_ai_config,
    resolve_capability,
    set_ai_config,
    decrypt_api_key,
)

router = APIRouter()


class AIConfigIn(BaseModel):
    # Satu provider + satu API key; endpoint boleh beda per kemampuan.
    endpoint_chat: Optional[str] = None
    endpoint_transcribe: Optional[str] = None
    endpoint_rerank: Optional[str] = None
    model_transcribe: Optional[str] = None
    # None = "jangan ubah": mengirim API key baru otomatis mengaktifkan AI.
    enabled: Optional[bool] = None
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

    if response.status_code in (401, 403):
        # Tanpa API key tetap boleh: admin bisa mengisi model manual.
        return {
            "provider": provider,
            "base_url": base_url,
            "cached": False,
            "count": 0,
            "models": [],
            "warning": (
                "Provider menolak permintaan tanpa API key. Isi nama model manual "
                "atau simpan API key lalu muat ulang."
            ),
        }
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
    try:
        cfg = await set_ai_config(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    capability: str = "chat",
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Uji satu kemampuan: chat, regenerate, transcribe, atau rerank.

    Endpoint & model diambil dari `resolve_capability` (satu API key provider).
    """
    import io
    import time
    import wave

    import httpx

    cfg = await get_ai_config(db)
    name = capability if capability in ("chat", "regenerate", "transcribe", "rerank") else "chat"
    cap = resolve_capability(cfg, name)
    if not cap.get("url"):
        raise HTTPException(status_code=400, detail="Endpoint provider belum diketahui.")

    key = decrypt_api_key(cfg.get("api_key_enc"))
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    started = time.monotonic()
    output = ""
    try:
        if name == "transcribe":
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00" * 8000)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    cap["url"],
                    headers=headers,
                    data={"model": cap["model"] or "whisper-1"},
                    files={"file": ("silence.wav", buffer.getvalue(), "audio/wav")},
                )
            if response.status_code >= 400:
                raise RuntimeError(f"{response.status_code}: {response.text[:200]}")
            output = (response.json() or {}).get("text", "") or "(audio diterima)"
        elif name == "rerank":
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    cap["url"],
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": cap["model"],
                        "query": "cara produktif tanpa burnout",
                        "documents": [
                            "produktivitas dan fokus harian",
                            "resep kue coklat",
                        ],
                    },
                )
            if response.status_code >= 400:
                raise RuntimeError(f"{response.status_code}: {response.text[:200]}")
            payload = response.json() or {}
            results = payload.get("results") or payload.get("data") or []
            output = "; ".join(
                f"{item.get('index')}={round(float(item.get('relevance_score') or 0), 4)}"
                for item in results
                if isinstance(item, dict)
            ) or str(payload)[:300]
        else:
            from openai import AsyncOpenAI

            base = cap["url"].split("/chat/completions")[0]
            client = AsyncOpenAI(
                api_key=key or "sk-no-key-provided",
                base_url=base,
                timeout=float(cfg.get("timeout_seconds") or 90),
                max_retries=0,
            )
            response = await client.chat.completions.create(
                model=cap["model"] or cfg.get("model_metadata"),
                messages=[
                    {"role": "system", "content": "Balas satu kata: pong."},
                    {"role": "user", "content": "ping"},
                ],
                max_tokens=32,
                temperature=0,
            )
            output = (response.choices[0].message.content or "").strip() or "(kosong)"
    except Exception as exc:  # noqa: BLE001 - tampilkan penyebab ke admin
        elapsed = round(time.monotonic() - started, 2)
        log_text = "\n".join(
            [
                f"Kemampuan : {name}",
                f"Endpoint  : {cap['url']}",
                f"Model     : {cap['model'] or '-'}",
                f"Durasi    : {elapsed}s",
                f"Error     : {str(exc)[:400]}",
            ]
        )
        raise HTTPException(status_code=502, detail={"message": str(exc)[:300], "log_text": log_text}) from exc

    elapsed = round(time.monotonic() - started, 2)
    log_text = "\n".join(
        [
            f"Kemampuan : {name}",
            f"Endpoint  : {cap['url']}",
            f"Model     : {cap['model'] or '-'}",
            f"Durasi    : {elapsed}s",
            "Status    : OK",
            f"Output    : {output[:400]}",
        ]
    )
    return {
        "ok": True,
        "capability": name,
        "endpoint": cap["url"],
        "model": cap["model"],
        "elapsed": elapsed,
        "output": output[:600],
        "log_text": log_text,
    }


class PromptIn(BaseModel):
    key: str
    text: str = ""
    ctx: dict = {}


@router.get("/ai/prompts")
async def read_prompts(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Daftar prompt efektif + default + meta + riwayat perubahan."""
    data = await ai_prompts.get_prompts(db)
    data["history"] = await ai_prompts.get_history(db)
    return data


@router.put("/ai/prompts")
async def save_prompt(
    payload: PromptIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        data = await ai_prompts.save_prompt(
            db, payload.key, payload.text, updated_by=current_admin.email
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="ai_prompt_updated",
            resource_type="platform_setting",
            resource_id=f"ai_prompt:{payload.key}",
            new_values={"chars": len(payload.text or "")},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    data["history"] = await ai_prompts.get_history(db)
    return data


@router.post("/ai/prompts/{key}/reset")
async def reset_prompt(
    key: str,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    try:
        data = await ai_prompts.reset_prompt(db, key, updated_by=current_admin.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=current_admin.id,
            actor_email=current_admin.email,
            action="ai_prompt_reset",
            resource_type="platform_setting",
            resource_id=f"ai_prompt:{key}",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await db.commit()
    data["history"] = await ai_prompts.get_history(db)
    return data


@router.post("/ai/prompts/{key}/preview")
async def preview_prompt(
    key: str,
    payload: PromptIn,
    db: AsyncSession = Depends(get_db_session),
):
    """Render prompt dengan sample context (tanpa memanggil model)."""
    data = await ai_prompts.get_prompts(db)
    try:
        return ai_prompts.preview(
            key,
            payload.text if payload.text is not None else None,
            payload.ctx or None,
            data["prompts"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ai/prompts/{key}/test")
async def test_prompt(
    key: str,
    payload: PromptIn,
    db: AsyncSession = Depends(get_db_session),
):
    """Kirim prompt (hasil render) ke model aktif, kembalikan output + log."""
    import time as _time

    data = await ai_prompts.get_prompts(db)
    try:
        rendered = ai_prompts.preview(
            key,
            payload.text if payload.text is not None else None,
            payload.ctx or None,
            data["prompts"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cfg = await get_ai_config(db)
    if not ai_is_configured(cfg):
        raise HTTPException(status_code=400, detail="AI belum aktif / API key kosong.")

    text = str(rendered.get("rendered") or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Prompt kosong. Isi dulu atau pilih default.",
        )
    messages: List[Dict[str, Any]] = []
    if key.endswith("_system"):
        messages = [
            {"role": "system", "content": text},
            {"role": "user", "content": "Balas JSON singkat sesuai instruksi di sistem."},
        ]
    else:
        messages = [
            {"role": "system", "content": ai_prompts.get_sync("metadata_system")},
            {"role": "user", "content": text},
        ]

    started = _time.time()
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=decrypt_api_key(cfg.get("api_key_enc")) or "sk-no-key",
            base_url=effective_base_url(cfg),
            timeout=float(cfg.get("timeout_seconds") or 90),
            max_retries=0,
        )
        response = await client.chat.completions.create(
            model=str(cfg.get("model_metadata") or ""),
            messages=cast(Any, messages),
            temperature=float(cfg.get("temperature") or 0.7),
            max_tokens=min(800, int(cfg.get("max_tokens") or 800)),
        )
        output = (response.choices[0].message.content or "").strip()
        error = ""
    except Exception as exc:  # noqa: BLE001
        output = ""
        error = str(exc)[:400]

    elapsed = round(_time.time() - started, 1)
    log_text = "\n".join(
        [
            f"Prompt     : {key}",
            f"Model      : {cfg.get('provider')} / {cfg.get('model_metadata')}",
            f"Durasi     : {elapsed}s",
            f"Status     : {'OK' if output else 'GAGAL'}",
            "",
            "--- prompt terkirim ---",
            text[:4000],
            "",
            "--- output ---",
            output[:4000] or f"(kosong) {error}",
        ]
    )
    if not output:
        raise HTTPException(status_code=502, detail={"message": error, "log_text": log_text})
    return {"ok": True, "output": output, "elapsed": elapsed, "log_text": log_text}
