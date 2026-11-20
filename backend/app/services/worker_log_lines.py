"""Penyimpanan baris log worker (streaming dari dalam instance)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_log_line import WorkerLogLine

logger = logging.getLogger(__name__)

MAX_MESSAGE = 20000
MAX_BATCH = 800

# Noise dari Docker/Vast: instance sudah dihapus saat log dibaca — bukan
# kegagalan task, jadi tidak perlu masuk dashboard.
_DROP_MARKERS = ("no such container", "error response from daemon")

# Stack trace Go (helper internal image) bisa ratusan baris dan membanjiri log.
# Cukup tampilkan satu baris penanda, sisanya dibuang.
_STACK_LINE = re.compile(
    r"^(goroutine \d+"
    r"|created by "
    r"|runtime\."
    r"|/usr/local/go/src/"
    r"|\s+/usr/local/go/src/"
    r"|[a-z0-9_.$]+\(0x[0-9a-f]+)",
    re.IGNORECASE,
)
_STACK_HINT = "[worker] stack trace internal disembunyikan (tidak memengaruhi task)"


def _clean(value: Any, limit: int = MAX_MESSAGE) -> str:
    return str(value or "")[:limit]


async def append_lines(
    db: AsyncSession,
    *,
    task_id: Optional[str],
    instance_id: Optional[int],
    lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows = []
    stack_hint_done = False
    for offset, item in enumerate((lines or [])[:MAX_BATCH]):
        if not isinstance(item, dict):
            continue
        try:
            seq = int(item.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        message = _clean(item.get("message"))
        lowered = message.lower()
        if any(marker in lowered for marker in _DROP_MARKERS):
            continue
        if _STACK_LINE.match(message.strip()):
            if not stack_hint_done:
                stack_hint_done = True
                rows.append(
                    {
                        "task_id": task_id,
                        "instance_id": instance_id,
                        "seq": seq if seq > 0 else offset + 1,
                        "level": "INFO",
                        "stage": None,
                        "message": _STACK_HINT,
                    }
                )
            continue
        rows.append(
            {
                "task_id": task_id,
                "instance_id": instance_id,
                "seq": seq if seq > 0 else offset + 1,
                "level": _clean(item.get("level") or "INFO", 16).upper(),
                "stage": _clean(item.get("stage") or "", 40) or None,
                "message": message,
            }
        )
    if not rows:
        return {"stored": 0, "max_seq": 0}
    if task_id is None:
        db.add_all([WorkerLogLine(**row) for row in rows])
        await db.commit()
        return {"stored": len(rows), "max_seq": max(row["seq"] for row in rows)}
    statement = pg_insert(WorkerLogLine).values(rows).on_conflict_do_nothing(
        index_elements=["task_id", "seq"]
    )
    result = await db.execute(statement)
    await db.commit()
    return {
        "stored": int(result.rowcount or 0),
        "max_seq": max(row["seq"] for row in rows),
    }


async def list_lines(
    db: AsyncSession,
    *,
    task_id: Optional[str] = None,
    after_seq: int = 0,
    limit: int = 500,
    level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # Tanpa after_seq: ambil N TERBARU (desc) lalu dibalik agar UI melihat
    # baris terakhir tanpa kehilangan log baru di luar limit.
    query = select(WorkerLogLine).order_by(
        WorkerLogLine.seq.asc() if after_seq else WorkerLogLine.seq.desc()
    )
    if task_id:
        query = query.where(WorkerLogLine.task_id == task_id)
    if after_seq:
        query = query.where(WorkerLogLine.seq > after_seq)
    if level:
        query = query.where(WorkerLogLine.level == level.upper())
    # Batas atas 5000: admin perlu riwayat penuh untuk diagnosis, bukan 200
    # baris terakhir saja (log boto3/ffmpeg bisa ribuan baris).
    rows = (await db.execute(query.limit(min(5000, max(1, limit))))).scalars().all()
    if not after_seq:
        rows = list(reversed(rows))
    return [
        {
            "id": str(row.id),
            "task_id": str(row.task_id) if row.task_id else None,
            "instance_id": row.instance_id,
            "seq": row.seq,
            "level": row.level,
            "stage": row.stage,
            "message": row.message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


async def clear(db: AsyncSession, task_id: Optional[str] = None) -> int:
    statement = delete(WorkerLogLine)
    if task_id:
        statement = statement.where(WorkerLogLine.task_id == task_id)
    result = await db.execute(statement)
    await db.commit()
    return int(result.rowcount or 0)
