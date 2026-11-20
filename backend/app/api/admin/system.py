"""
Admin system health + statistik NYATA untuk Overview.

Tidak ada lagi data contoh: semua angka dihitung dari database (users, tasks,
clips, transaksi, worker_instances). Dua endpoint:

  GET /api/admin/system/stats    -> kartu KPI + task terbaru (dipakai Overview)
  GET /api/admin/system/metrics  -> deret waktu untuk grafik (30 hari)

Catatan performa: query memakai agregasi di database (count/sum/date_trunc),
bukan menarik semua baris ke Python.
"""
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.clip import Clip
from app.models.pricing_plan import PricingPlan
from app.models.task import Task, TaskStatus
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.models.worker_instance import WorkerInstance

router = APIRouter(dependencies=[Depends(get_current_admin)])

# Uptime proses API (dipakai tab System: "backend sudah jalan X").
_API_STARTED = time.monotonic()

# Status yang dianggap "gagal" untuk menghitung error rate.
FAILED_STATUSES = (TaskStatus.ERROR.value, TaskStatus.CANCELLED.value)


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db_session)):
    started = time.monotonic()
    try:
        await db.execute(text("select 1"))
        db_ok = True
    except Exception:  # pragma: no cover - hanya saat DB benar-benar mati
        db_ok = False
    db_latency_ms = int((time.monotonic() - started) * 1000)

    from app.core.config import get_settings

    settings = get_settings()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
        "database_latency_ms": db_latency_ms,
        "version": settings.APP_VERSION,
        "environment": "production" if not settings.DEBUG else "development",
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def system_stats(db: AsyncSession = Depends(get_db_session)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    banned_users = (
        await db.execute(select(func.count(User.id)).where(User.is_banned.is_(True)))
    ).scalar() or 0
    total_tasks = (await db.execute(select(func.count(Task.id)))).scalar() or 0
    total_clips = (await db.execute(select(func.count(Clip.id)))).scalar() or 0
    credits_spent = (
        await db.execute(select(func.coalesce(func.sum(Task.credits_spent), 0)))
    ).scalar() or 0

    # Transaksi sukses = pendapatan.
    revenue_paid = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.status == TransactionStatus.SUCCESS.value
            )
        )
    ).scalar() or 0

    status_rows = (
        await db.execute(select(Task.status, func.count(Task.id)).group_by(Task.status))
    ).all()
    by_status = {getattr(s, "value", str(s)): int(c) for s, c in status_rows}

    since = datetime.now(timezone.utc) - timedelta(days=14)
    day_rows = (
        await db.execute(
            select(func.date_trunc("day", Task.created_at).label("day"), func.count(Task.id))
            .where(Task.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    tasks_per_day = [
        {"date": day.date().isoformat() if day else None, "count": int(count)}
        for day, count in day_rows
    ]

    recent_rows = (
        await db.execute(
            select(Task, User.email)
            .join(User, Task.user_id == User.id, isouter=True)
            .order_by(Task.created_at.desc())
            .limit(8)
        )
    ).all()
    recent_tasks = [
        {
            "id": str(task.id),
            "source_type": task.source_type,
            "source_url": task.source_url,
            "status": getattr(task.status, "value", str(task.status)),
            "progress": task.progress,
            "total_clips": task.total_clips,
            "credits_spent": task.credits_spent,
            "user_email": email,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        for task, email in recent_rows
    ]

    completed = int(by_status.get(TaskStatus.COMPLETED.value, 0))
    failed = sum(int(by_status.get(s, 0)) for s in FAILED_STATUSES)
    finished = completed + failed

    return {
        "total_users": int(total_users),
        "banned_users": int(banned_users),
        "total_tasks": int(total_tasks),
        "total_clips": int(total_clips),
        "credits_spent": float(credits_spent),
        "revenue_paid": float(revenue_paid),
        "tasks_by_status": by_status,
        "tasks_per_day": tasks_per_day,
        "recent_tasks": recent_tasks,
        "completed_tasks": completed,
        "failed_tasks": failed,
        "error_rate": round(failed / finished * 100, 1) if finished else 0.0,
    }


@router.get("/metrics")
async def system_metrics(
    days: int = 30,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deret waktu untuk grafik Overview (default 30 hari).

    Mengembalikan daftar per-hari yang SUDAH diisi nol untuk hari tanpa data,
    supaya grafik tidak "bolong" dan sumbu X tetap konsisten.
    """
    days = max(7, min(days, 90))
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    async def series(column, model, extra_where=None):
        query = (
            select(func.date_trunc("day", column).label("day"), func.count())
            .where(column >= start)
            .group_by("day")
        )
        if extra_where is not None:
            query = query.where(extra_where)
        rows = (await db.execute(query)).all()
        return {day.date().isoformat(): int(count) for day, count in rows if day}

    tasks_map = await series(Task.created_at, Task)
    clips_map = await series(Clip.created_at, Clip)
    signups_map = await series(User.created_at, User)
    revenue_rows = (
        await db.execute(
            select(
                func.date_trunc("day", Transaction.created_at).label("day"),
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .where(Transaction.created_at >= start, Transaction.status == TransactionStatus.SUCCESS.value)
            .group_by("day")
        )
    ).all()
    revenue_map = {day.date().isoformat(): float(total) for day, total in revenue_rows if day}

    timeline = []
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        timeline.append(
            {
                "date": day,
                "tasks": tasks_map.get(day, 0),
                "clips": clips_map.get(day, 0),
                "signups": signups_map.get(day, 0),
                "revenue": revenue_map.get(day, 0.0),
            }
        )

    today_iso = now.date().isoformat()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start_dt = day_start - timedelta(days=6)
    credits_today = (
        await db.execute(
            select(func.coalesce(func.sum(Task.credits_spent), 0)).where(
                Task.created_at >= day_start
            )
        )
    ).scalar() or 0
    credits_week = (
        await db.execute(
            select(func.coalesce(func.sum(Task.credits_spent), 0)).where(
                Task.created_at >= week_start_dt
            )
        )
    ).scalar() or 0

    avg_duration = (
        await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Task.completed_at - Task.created_at)
                )
            ).where(Task.completed_at.isnot(None), Task.created_at >= start)
        )
    ).scalar()

    top_rows = (
        await db.execute(
            select(User.email, User.name, func.count(Task.id).label("tasks"))
            .join(Task, Task.user_id == User.id)
            .where(Task.created_at >= start)
            .group_by(User.email, User.name)
            .order_by(func.count(Task.id).desc())
            .limit(5)
        )
    ).all()

    active_workers = (
        await db.execute(
            select(func.count(WorkerInstance.id)).where(
                WorkerInstance.destroyed_at.is_(None)
            )
        )
    ).scalar() or 0

    plans_total = (await db.execute(select(func.count(PricingPlan.id)))).scalar() or 0

    from app.core.config import get_settings

    settings = get_settings()
    ai_configured = bool(settings.AI_API_KEY or settings.OPENAI_API_KEY)

    return {
        "days": days,
        "timeline": timeline,
        "today": today_iso,
        "credits_spent_today": float(credits_today),
        "credits_spent_week": float(credits_week),
        "avg_task_duration_seconds": int(avg_duration) if avg_duration else 0,
        "top_users": [
            {"email": email, "name": name, "tasks": int(tasks)} for email, name, tasks in top_rows
        ],
        "active_workers": int(active_workers),
        "plans_total": int(plans_total),
        "ai": {
            "configured": ai_configured,
            "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL,
        },
    }

@router.get("/host")
async def system_host(db: AsyncSession = Depends(get_db_session)):
    """
    Metrik VPS realtime (CPU, RAM, disk, load, jaringan, container).

    Sumber: agent host mengirim snapshot ke `/api/internal/host-metrics` tiap
    5 detik; endpoint ini mengembalikan snapshot terbaru + histori ringkas
    untuk grafik, plus antrean task agar admin tahu beban saat itu.
    """
    from app.core.config import get_settings
    from app.services import host_metrics as store

    data = store.snapshot()
    queued = (
        await db.execute(select(func.count(Task.id)).where(Task.status == TaskStatus.QUEUED))
    ).scalar() or 0
    processing = (
        await db.execute(select(func.count(Task.id)).where(Task.status == TaskStatus.PROCESSING))
    ).scalar() or 0
    workers_active = (
        await db.execute(
            select(func.count(WorkerInstance.id)).where(WorkerInstance.destroyed_at.is_(None))
        )
    ).scalar() or 0

    return {
        **data,
        "services": store.services_from((data.get("latest") or {}).get("containers") or []),
        "api_uptime_seconds": int(max(0, time.monotonic() - _API_STARTED)),
        "api_version": get_settings().APP_VERSION,
        "queue": {"queued": int(queued), "processing": int(processing)},
        "workers_active": int(workers_active),
    }



@router.get("/cleanup")
async def server_cleanup_status() -> Dict[str, Any]:
    """Estimasi sampah server (temp/log/cache/docker) tanpa menghapus apa pun."""
    from app.services import server_cleanup

    return server_cleanup.describe()


@router.post("/cleanup")
async def server_cleanup_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Bersihkan sampah server. `dry_run` default true (aman).

    Body: {"dry_run": bool, "targets": ["temp","logs","cache","docker"]}
    """
    from app.services import server_cleanup

    dry_run = bool(payload.get("dry_run", True))
    targets = payload.get("targets") or None
    result = await server_cleanup.cleanup_server(dry_run=dry_run, targets=targets)
    return result


@router.get("/actions")
async def system_actions():
    """Aksi host yang diizinkan + riwayat perintah terbaru."""
    from app.services import host_commands as commands

    return {"actions": commands.actions(), "jobs": commands.recent(20)}


@router.post("/actions")
async def run_system_action(payload: dict):
    """Antrekan aksi host (clear cache / restart caddy / prune docker).

    Dieksekusi oleh agent host `clipzi-host-commands.py` (systemd) karena
    container API tidak punya akses /proc host maupun docker socket.
    """
    from app.services import host_commands as commands

    action = str(payload.get("action") or "").strip()
    raw_args = payload.get("args") or []
    # `args` TIDAK boleh undefined: sebelumnya baris ini memakai variabel lokal
    # yang tidak pernah dibuat -> NameError -> seluruh endpoint balas HTTP 500
    # (inilah sebab tombol Clear Cache / Restart Caddy / Prune selalu gagal).
    args = [str(item) for item in raw_args] if isinstance(raw_args, list) else []
    try:
        job = commands.enqueue(action, requested_by="admin", args=args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@router.get("/actions/{job_id}")
async def read_system_action(job_id: str):
    from app.services import host_commands as commands

    job = commands.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Perintah tidak ditemukan")
    return job


_HOST_INFO_CACHE: Dict[str, Any] = {"at": 0.0, "data": None}
HOST_INFO_TTL = 600.0


async def _run_host_command(
    action: str, wait_seconds: float = 60.0, args: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Antrekan aksi host lalu tunggu hasil (agent polling 3 detik)."""
    import asyncio

    from app.services import host_commands as commands

    job = commands.enqueue(action, requested_by="admin")
    deadline = time.monotonic() + max(5.0, wait_seconds)
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        current = commands.get(job["id"])
        if current and current.get("status") in ("done", "error"):
            return current
    return commands.get(job["id"]) or job


@router.get("/host-info")
async def system_host_info():
    """Info OS host (distro, kernel, arch, core) — diambil via agent host."""
    import json

    cached = _HOST_INFO_CACHE
    if cached["data"] and time.monotonic() - float(cached["at"]) < HOST_INFO_TTL:
        return {**cached["data"], "cached": True}

    job = await _run_host_command("os_info", wait_seconds=20)
    raw = str(job.get("output") or "").strip()
    data: Dict[str, Any] = {}
    if raw:
        try:
            data = json.loads(raw.splitlines()[-1])
        except Exception:  # noqa: BLE001 - output bukan JSON
            data = {}
    if not data:
        return {
            "available": False,
            "error": raw[:400] or "agent host belum melaporkan info OS",
            "job": job.get("status"),
        }
    payload = {"available": True, "cached": False, **data}
    _HOST_INFO_CACHE.update({"at": time.monotonic(), "data": payload})
    return payload


@router.post("/speedtest")
async def system_speedtest():
    """Uji kecepatan internet host (unduh/unggah + latency) via agent."""
    import json

    job = await _run_host_command("speedtest", wait_seconds=90)
    raw = str(job.get("output") or "").strip()
    data: Dict[str, Any] = {}
    if raw:
        try:
            data = json.loads(raw.splitlines()[-1])
        except Exception:  # noqa: BLE001
            data = {}
    if not data:
        raise HTTPException(
            status_code=502,
            detail=(raw[:400] or "Speedtest gagal: agent host tidak merespons"),
        )
    down = float(data.get("down_bps") or 0) * 8 / 1_000_000
    up = float(data.get("up_bps") or 0) * 8 / 1_000_000
    return {
        "ok": True,
        **data,
        "down_mbps": round(down, 2),
        "up_mbps": round(up, 2),
        "taken_at": datetime.now(timezone.utc).isoformat(),
    }


import json
import re
from datetime import datetime, timezone

from pydantic import BaseModel

from app.models.migration_job import MigrationJob

BACKUP_NAME_RE = re.compile(r"^\d{8}T\d{6}Z$")


class RestoreIn(BaseModel):
    archive: str


def _job_row(job: MigrationJob) -> Dict[str, Any]:
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "archive": job.archive,
        "size_bytes": job.size_bytes,
        "detail": job.detail,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "created_by": job.created_by,
    }


def _last_json(raw: str) -> Dict[str, Any]:
    for line in reversed([item.strip() for item in (raw or "").splitlines() if item.strip()]):
        try:
            parsed = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


@router.get("/backups")
async def backups_overview(db: AsyncSession = Depends(get_db_session)):
    """Riwayat job backup/restore + daftar arsip di host."""
    rows = (
        await db.execute(select(MigrationJob).order_by(MigrationJob.created_at.desc()).limit(20))
    ).scalars().all()
    listing = await _run_host_command("list_backups", wait_seconds=20)
    archives = [
        line.strip()
        for line in str(listing.get("output") or "").splitlines()
        if BACKUP_NAME_RE.match(line.strip())
    ]
    return {
        "jobs": [_job_row(row) for row in rows],
        "archives": archives,
        "agent_status": listing.get("status"),
    }


@router.post("/backups")
async def create_backup(
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Jalankan backup penuh sekarang (DB + env + compose) lewat agent host."""
    job = MigrationJob(kind="backup", status="running", created_by=current_admin.email)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    result = await _run_host_command("backup_now", wait_seconds=900)
    raw = str(result.get("output") or "")
    data = _last_json(raw)
    ok = bool(result.get("ok")) and bool(data.get("ok", True))
    size = 0
    files = data.get("files")
    if isinstance(files, list):
        size = sum(int(item.get("size") or 0) for item in files if isinstance(item, dict))

    job.status = "success" if ok else "error"
    job.archive = (str(data.get("archive") or "")[:80]) or None
    job.size_bytes = size or None
    job.detail = str(
        data.get("error")
        or (f"Backup {job.archive} selesai ({round(size / 1048576, 2)} MB)" if ok else "Backup gagal")
    )[:900]
    job.log = raw[:12000]
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return {"ok": ok, "job": _job_row(job), "log_text": raw}


@router.post("/backups/restore")
async def restore_backup(
    payload: RestoreIn,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Pulihkan database + env dari arsip backup (validasi nama ketat)."""
    archive = str(payload.archive or "").strip()
    if not BACKUP_NAME_RE.match(archive):
        raise HTTPException(status_code=400, detail="Nama arsip tidak valid.")

    job = MigrationJob(
        kind="restore", status="running", archive=archive, created_by=current_admin.email
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    result = await _run_host_command("restore_backup", wait_seconds=1800, args=[archive])
    raw = str(result.get("output") or "")
    data = _last_json(raw)
    ok = bool(result.get("ok")) and bool(data.get("ok", True))

    job.status = "success" if ok else "error"
    job.detail = str(
        data.get("error") or ("Restore selesai. Restart layanan untuk memastikan state bersih." if ok else "Restore gagal")
    )[:900]
    job.log = raw[:12000]
    job.finished_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return {
        "ok": ok,
        "job": _job_row(job),
        "log_text": raw,
        "restart_hint": "docker compose -f docker-compose.vps.yml up -d --force-recreate api admin web",
    }
