"""Admin API - pengaturan runner downloader (fallback GitHub Actions)."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.download_runner import DownloadRunner
from app.models.user import User
from app.services import runner_manager

router = APIRouter(dependencies=[Depends(get_current_admin)])


class RunnerIn(BaseModel):
    name: str = Field(max_length=80)
    owner: str = Field(max_length=120)
    repo: str = Field(max_length=120)
    workflow_file: str = Field(default="downloader_video.yml", max_length=160)
    git_ref: str = Field(default="main", max_length=80)
    auth_mode: str = Field(default="pat", max_length=10)
    token: Optional[str] = Field(default=None, description="Hanya ditulis, tidak pernah dibaca")
    weight: int = Field(default=100, ge=1, le=1000)
    enabled: bool = True


class RunnerPatch(BaseModel):
    name: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    workflow_file: Optional[str] = None
    git_ref: Optional[str] = None
    auth_mode: Optional[str] = None
    token: Optional[str] = None
    weight: Optional[int] = None
    enabled: Optional[bool] = None
    status: Optional[str] = None


def _audit(db: AsyncSession, request: Request, admin: User, action: str, runner_id: str, meta=None):
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="download_runner",
            resource_id=runner_id,
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("/stats")
async def runner_stats(db: AsyncSession = Depends(get_db_session)):
    """Ringkasan downloader untuk admin (monitoring)."""
    from sqlalchemy import func

    from app.models.download_log import DownloadAttempt
    from app.models.task import Task

    status_rows = (
        await db.execute(
            select(Task.download_status, func.count(Task.id)).group_by(Task.download_status)
        )
    ).all()
    by_status = {(row[0] or "unknown"): int(row[1]) for row in status_rows}
    runners = await runner_manager.list_runners(db)
    active = sum(1 for item in runners if item.enabled and item.status == "active")
    attempts = (await db.execute(select(func.count(DownloadAttempt.id)))).scalar() or 0
    return {
        "downloads": by_status,
        "runners": {
            "total": len(runners),
            "active": active,
            "disabled": sum(1 for item in runners if not item.enabled),
        },
        "attempts": int(attempts),
    }


@router.get("/")
async def list_runners(db: AsyncSession = Depends(get_db_session)):
    rows = await runner_manager.list_runners(db)
    return {"items": [runner_manager.serialize_runner(item) for item in rows]}


@router.post("/")
async def create_runner(
    payload: RunnerIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    existing = (
        await db.execute(select(DownloadRunner).where(DownloadRunner.name == payload.name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Nama runner sudah dipakai.")
    data = payload.model_dump()
    data["token"] = data.pop("token", None)
    runner = await runner_manager.create_runner(db, data)
    _audit(db, request, current_admin, "runner_created", str(runner.id), {"name": runner.name})
    await db.commit()
    return runner_manager.serialize_runner(runner)


@router.patch("/{runner_id}")
async def update_runner(
    runner_id: UUID,
    payload: RunnerPatch,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    runner = await db.get(DownloadRunner, runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner tidak ditemukan.")
    data = payload.model_dump(exclude_unset=True)
    runner = await runner_manager.update_runner(db, runner, data)
    _audit(db, request, current_admin, "runner_updated", str(runner.id))
    await db.commit()
    return runner_manager.serialize_runner(runner)


class WorkflowInstallIn(BaseModel):
    """Opsi pemasangan workflow (force = timpa file yang berbeda)."""

    force: bool = False


@router.get("/{runner_id}/workflow")
async def get_runner_workflow(
    runner_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    runner = await db.get(DownloadRunner, runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner tidak ditemukan.")
    return await runner_manager.workflow_status(db, runner)


@router.post("/{runner_id}/workflow")
async def install_runner_workflow(
    runner_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
    payload: Optional[WorkflowInstallIn] = None,
):
    """Pasang/perbarui file workflow di repo runner (commit langsung ke default branch)."""
    runner = await db.get(DownloadRunner, runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner tidak ditemukan.")
    try:
        result = await runner_manager.install_workflow(
            db, runner, force=bool(payload.force) if payload else False
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    _audit(
        db,
        request,
        current_admin,
        "runner_workflow_installed",
        str(runner.id),
        {"action": result.get("action"), "path": result.get("path")},
    )
    await db.commit()
    return result


@router.post("/{runner_id}/test")
async def test_runner(
    runner_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    runner = await db.get(DownloadRunner, runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner tidak ditemukan.")
    return await runner_manager.check_runner(db, runner)


@router.delete("/{runner_id}")
async def delete_runner(
    runner_id: UUID,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    runner = await db.get(DownloadRunner, runner_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Runner tidak ditemukan.")
    _audit(db, request, current_admin, "runner_deleted", str(runner.id), {"name": runner.name})
    await db.delete(runner)
    await db.commit()
    return {"message": "Runner dihapus.", "id": str(runner_id)}
