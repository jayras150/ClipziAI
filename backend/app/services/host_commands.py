"""
Antrean perintah untuk agent host (VPS).

Container API tidak punya akses CPU/disk *host* maupun docker socket, jadi aksi
seperti "Clear Cache VPS" atau "Restart Caddy" dieksekusi oleh agent kecil yang
berjalan di host (`clipzi-host-commands.py`, systemd).

Alur:
  admin -> POST /api/admin/system/actions {action}
        -> job masuk antrean (status=pending)
  agent -> GET  /api/internal/host-commands?agent=<host>   (klaim job)
        -> POST /api/internal/host-commands/{id}/result     (ok + output)

Antrean disimpan di memori (API satu proses, pola sama dengan
`YOUTUBE_UPLOAD_JOBS`). Whitelist keras: agent tidak menerima shell bebas.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Hanya aksi ini yang boleh dieksekusi agent (didefinisikan juga di agent).
ACTIONS: Dict[str, Dict[str, str]] = {
    "clear_cache": {
        "label": "Clear cache VPS",
        "command": "sync; echo 3 > /proc/sys/vm/drop_caches",
        "description": "Membuang page cache/buffer RAM (aman, tidak menghapus data).",
    },
    "restart_caddy": {
        "label": "Restart Caddy",
        "command": "docker restart clipzi-caddy",
        "description": "Merestart reverse proxy Caddy.",
    },
    "prune_docker": {
        "label": "Prune Docker",
        "command": "docker builder prune -af",
        "description": "Membersihkan build cache Docker yang menumpuk.",
    },
}

MAX_OUTPUT = 4000
JOB_TTL = timedelta(hours=2)
MAX_JOBS = 100

_JOBS: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _cleanup() -> None:
    """Buang job lama supaya memori tidak tumbuh tanpa batas."""
    if len(_JOBS) <= MAX_JOBS:
        return
    ordered = sorted(_JOBS.values(), key=lambda item: item.get("created_at") or "")
    for job in ordered[: max(0, len(ordered) - MAX_JOBS)]:
        _JOBS.pop(str(job["id"]), None)


def enqueue(action: str, requested_by: str | None = None) -> Dict[str, Any]:
    key = str(action or "").strip()
    if key not in ACTIONS:
        raise ValueError(f"Aksi tidak dikenal: {action}")
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "action": key,
        "label": ACTIONS[key]["label"],
        "status": "pending",
        "output": "",
        "ok": None,
        "agent": None,
        "requested_by": requested_by,
        "created_at": _now(),
        "started_at": None,
        "finished_at": None,
    }
    _JOBS[job_id] = job
    _cleanup()
    logger.warning("Host command %s (%s) diantrekan oleh %s", key, job_id, requested_by)
    return dict(job)


def pending_for(agent: str | None = None) -> List[Dict[str, Any]]:
    """Ambil job yang belum diklaim, lalu tandai `running`."""
    claimed: List[Dict[str, Any]] = []
    for job in _JOBS.values():
        if job["status"] != "pending":
            continue
        job["status"] = "running"
        job["agent"] = agent or "host"
        job["started_at"] = _now()
        claimed.append(
            {
                "id": job["id"],
                "action": job["action"],
                "command": ACTIONS[job["action"]]["command"],
            }
        )
    return claimed


def finish(job_id: str, ok: bool, output: str) -> Optional[Dict[str, Any]]:
    job = _JOBS.get(str(job_id))
    if job is None:
        return None
    job["status"] = "done" if ok else "error"
    job["ok"] = bool(ok)
    job["output"] = str(output or "")[:MAX_OUTPUT]
    job["finished_at"] = _now()
    return dict(job)


def get(job_id: str) -> Optional[Dict[str, Any]]:
    job = _JOBS.get(str(job_id))
    return dict(job) if job else None


def recent(limit: int = 20) -> List[Dict[str, Any]]:
    ordered = sorted(_JOBS.values(), key=lambda item: item.get("created_at") or "", reverse=True)
    return [dict(job) for job in ordered[: max(1, min(50, limit))]]


def actions() -> List[Dict[str, str]]:
    return [
        {"id": key, "label": value["label"], "description": value["description"]}
        for key, value in ACTIONS.items()
    ]


__all__ = ["ACTIONS", "actions", "enqueue", "finish", "get", "pending_for", "recent"]
