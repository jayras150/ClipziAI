"""
Kirim event worker ke API (signed HMAC) — pengganti webhook Vast yang tidak ada.

Dipanggil dari pipeline (stage/done/error). Kegagalan pengiriman tidak pernah
menggagalkan pipeline: ini hanya observability/sinyal supervisor.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def report_worker_event(
    task_id: Any,
    event: str,
    *,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
) -> None:
    url = (settings.CLIPZI_CALLBACK_URL or "").strip()
    token = (settings.CLIPZI_WORKER_TOKEN or "").strip()
    if not url or not token:
        return

    payload = {
        "task_id": str(task_id),
        "event": event,
        "stage": stage,
        "progress": progress,
        "message": (message or "")[:500] or None,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(token.encode(), body, hashlib.sha256).hexdigest()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Clipzi-Signature": f"sha256={signature}",
                },
            )
    except Exception as exc:  # tidak boleh mengganggu pipeline
        logger.debug("Callback worker gagal (%s): %s", event, str(exc)[:200])
