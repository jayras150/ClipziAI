"""Penyimpanan baris log worker (streaming dari dalam instance)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker_log_line import WorkerLogLine

logger = logging.getLogger(__name__)

MAX_MESSAGE = 4000
MAX_BATCH = 300


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
    for offset, item in enumerate((lines or [])[:MAX_BATCH]):
        if not isinstance(item, dict):
            continue
        try:
            seq = int(item.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        rows.append(
            {
                "task_id": task_id,
                "instance_id": instance_id,
                "seq": seq if seq > 0 else offset + 1,
                "level": _clean(item.get("level") or "INFO", 16).upper(),
                "stage": _clean(item.get("stage") or "", 40) or None,
                "message": _clean(item.get("message")),
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
    limit: int = 200,
    level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = select(WorkerLogLine).order_by(WorkerLogLine.seq.asc())
    if task_id:
        query = query.where(WorkerLogLine.task_id == task_id)
    if after_seq:
        query = query.where(WorkerLogLine.seq > after_seq)
    if level:
        query = query.where(WorkerLogLine.level == level.upper())
    rows = (await db.execute(query.limit(min(1000, max(1, limit))))).scalars().all()
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
