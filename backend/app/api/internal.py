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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.models.worker_instance import WorkerInstance

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkerEvent(BaseModel):
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

    if row is not None:
        if payload.event in {"boot", "started"}:
            row.state = "worker_started"
        elif payload.event in {"error", "llm_failed"}:
            row.state = "worker_error"
            row.status_msg = (payload.message or payload.event)[:1000]
        if payload.stage == "logs" and payload.message:
            # URL bundle log (qurl.sh) — disimpan agar admin bisa mengunduh kapan pun.
            row.log_tail = payload.message[:4000]
        elif payload.stage:
            detail = payload.message or ""
            row.status_msg = (
                f"{payload.stage}: {detail}" if detail else f"stage:{payload.stage}"
            )[:1000]
        await db.commit()

    return {"ok": True}
