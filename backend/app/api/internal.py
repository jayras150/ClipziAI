"""
Endpoint internal untuk worker GPU (webhook milik kita sendiri).

Vast.ai tidak menyediakan webhook, jadi container worker mengirim event singkat
ke API saat boot/selesai/error. Supervisor instance memakai sinyal ini untuk
membedakan "instance hidup tapi onstart mati" dari "sedang bekerja".

Keamanan: body ditandatangani HMAC-SHA256 dengan `CLIPZI_WORKER_TOKEN`
(header `X-Clipzi-Signature: sha256=<hex>`). Tanpa token, endpoint menolak semua
permintaan (503) supaya tidak ada jalur tanpa autentikasi.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.models.worker_instance import WorkerInstance

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_agent_token(request: Request) -> None:
    """Autentikasi agent host (domain sync). Token sama dengan worker token."""
    token = (get_settings().CLIPZI_WORKER_TOKEN or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent token is not configured (CLIPZI_WORKER_TOKEN).",
        )
    provided = (request.headers.get("x-clipzi-token") or "").strip()
    if not provided or not hmac.compare_digest(token, provided):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


class HostMetricsIn(BaseModel):
    """Snapshot metrik host dari agent (bebas bentuk, divalidasi di service)."""

    ts: float | None = None
    hostname: str | None = None
    cpu: dict | None = None
    memory: dict | None = None
    disk: dict | None = None
    load: dict | None = None
    uptime_seconds: float | None = None
    network: dict | None = None
    containers: list | None = None
    docker: dict | None = None


class DomainAppliedIn(BaseModel):
    domain: str
    admin_domain: str | None = None
    ok: bool = True
    error: str | None = None


@router.get("/domain-task")
async def domain_task(request: Request, db: AsyncSession = Depends(get_db_session)):
    """
    Dipakai `deploy/clipzi-domain-sync.sh` di VPS: membaca permintaan ganti
    domain yang masih pending. Kosong = tidak ada pekerjaan.
    """
    from app.services import platform_config as pc

    _verify_agent_token(request)
    config = await pc.get_platform_config(db)
    if config.get("domain_status") != "pending" or not config.get("pending_domain"):
        return {"pending": False}
    return {
        "pending": True,
        "domain": config.get("pending_domain"),
        "admin_domain": config.get("pending_admin_domain"),
        "requested_at": config.get("domain_requested_at"),
        "current_site_url": pc.site_url(config),
    }


@router.post("/domain-applied")
async def domain_applied(
    payload: DomainAppliedIn,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Laporan hasil penerapan domain oleh agent host."""
    from app.services import platform_config as pc

    _verify_agent_token(request)
    if payload.ok:
        config = await pc.set_platform_config(
            db,
            {
                "site_url": f"https://{payload.domain}",
                "admin_url": (
                    f"https://{payload.admin_domain}" if payload.admin_domain else None
                ),
                "applied_domain": payload.domain,
                "pending_domain": None,
                "pending_admin_domain": None,
                "domain_status": "applied",
                "domain_applied_at": datetime.now(timezone.utc).isoformat(),
                "domain_last_error": None,
            },
        )
        pc.apply_platform_config_to_env(config)
        return {"status": "applied", "site_url": pc.site_url(config)}

    await pc.set_platform_config(
        db, {"domain_status": "failed", "domain_last_error": (payload.error or "")[:500]}
    )
    return {"status": "failed"}


class WorkerEvent(BaseModel):
    """Event singkat yang dikirim worker (boot/stage/done/error).

    Dulu deklarasi `class` ini sempat hilang sehingga nama `WorkerEvent` tidak
    pernah ada; handler menangkap NameError sebagai payload invalid dan
    membalas **400** untuk semua callback worker (boot tidak pernah tercatat,
    supervisor mengira worker tidak pernah start).
    """

    task_id: str
    event: str                      # boot | started | stage | done | error
    instance_id: int | None = None
    stage: str | None = None
    progress: int | None = None
    message: str | None = None


def _verify_signature(body: bytes, signature: str) -> None:
    token = (get_settings().CLIPZI_WORKER_TOKEN or "").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker callback is not configured (CLIPZI_WORKER_TOKEN).",
        )
    expected = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=").strip()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )


@router.post("/worker/events")
async def worker_events(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    body = await request.body()
    _verify_signature(body, request.headers.get("x-clipzi-signature", ""))

    try:
        payload = WorkerEvent(**json.loads(body or b"{}"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payload: {exc}"
        ) from exc

    logger.info(
        "Worker event: task=%s event=%s stage=%s progress=%s",
        payload.task_id,
        payload.event,
        payload.stage,
        payload.progress,
    )

    row = None
    if payload.instance_id:
        row = (
            await db.execute(
                select(WorkerInstance)
                .where(WorkerInstance.instance_id == payload.instance_id)
                .order_by(WorkerInstance.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if row is None:
        # Worker biasanya tidak tahu instance id-nya (env onstart dibuat sebelum
        # instance ada), jadi cari baris terakhir milik task ini.
        try:
            task_uuid = UUID(str(payload.task_id))
        except Exception:
            task_uuid = None
        if task_uuid is not None:
            row = (
                await db.execute(
                    select(WorkerInstance)
                    .where(WorkerInstance.task_id == task_uuid)
                    .order_by(WorkerInstance.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

    if row is not None:
        if payload.event in {"boot", "started"}:
            row.state = "worker_started"
        elif payload.event in {"error", "llm_failed"}:
            row.state = "worker_error"
            row.status_msg = (payload.message or payload.event)[:1000]
        # Tahap yang informasinya harus tetap tersimpan (tidak tertimpa tahap
        # berikutnya): status LLM/CUDA, rerank, dan kegagalan unggah log.
        note_stages = {
            "llm_info",
            "llm_perf",
            "llm_failed",
            "rerank_skipped",
            "logs_failed",
        }
        if payload.stage == "logs" and payload.message:
            # URL bundle log (qurl.sh) ditaruh paling atas, catatan llm_info tetap ada.
            existing = (row.log_tail or "").strip()
            row.log_tail = (
                f"LOG_URL={payload.message}" + (f"\n{existing}" if existing else "")
            )[:4000]
        elif payload.stage in note_stages:
            note = f"[{payload.stage}] {(payload.message or '').strip()}"[:800]
            existing = row.log_tail or ""
            row.log_tail = (f"{existing}\n{note}" if existing else note)[:4000]
        elif payload.stage:
            detail = payload.message or ""
            row.status_msg = (
                f"{payload.stage}: {detail}" if detail else f"stage:{payload.stage}"
            )[:1000]
        await db.commit()

    return {"ok": True}

@router.post("/host-metrics")
async def host_metrics(
    payload: HostMetricsIn,
    request: Request,
):
    """
    Terima snapshot metrik VPS dari agent host (timer 5 detik).

    Disimpan di memori proses API; dipakai dashboard System untuk tampilan
    realtime tanpa memberi container akses ke docker socket atau /proc host.
    """
    from app.services import host_metrics as store

    _verify_agent_token(request)
    sample = store.record(payload.model_dump(exclude_none=True))
    return {"ok": True, "ts": sample["ts"]}

@router.get("/proxies/active.txt", response_class=PlainTextResponse)
async def active_proxies(request: Request, db: AsyncSession = Depends(get_db_session)):
    """File proxy aktif untuk worker (fallback bila env YTDLP_PROXY_POOL kosong)."""
    from app.services import proxy_pool

    _verify_agent_token(request)
    pool = await proxy_pool.get_pool(db)
    return PlainTextResponse(pool.get("active_txt") or "", media_type="text/plain; charset=utf-8")

