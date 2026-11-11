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
import os
from typing import Any, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def instance_id_from_env() -> Optional[int]:
    """Ambil id instance dari environment container Vast.

    Vast menamai container `C.<instance_id>` (mis. `C.60248471`) dan menaruhnya
    di `VAST_CONTAINERLABEL`. Dipakai agar callback bisa menyertakan instance_id
    sehingga API bisa mencocokkan baris `worker_instances` dengan tepat.
    """
    for key in ("CLIPZI_INSTANCE_ID", "VAST_CONTAINERLABEL", "CONTAINER_ID"):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        digits = "".join(ch for ch in raw.split(".")[-1] if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                continue
    return None


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
        "instance_id": instance_id_from_env(),
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
