"""
Runner Manager: fallback downloader via GitHub Actions.

Alur (Vast tetap downloader utama):
  worker gagal download (retryable) → POST /api/internal/downloader/fallback
  → pilih runner sehat (weighted + cooldown) → workflow_dispatch
  → workflow ambil cookies & presigned upload dari /context → yt-dlp
  → upload ke storage → POST /callback (token job) → task lanjut clipping.

Credential runner disimpan terenkripsi dan tidak pernah dikembalikan ke UI/log.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_field, encrypt_field
from app.models.download_runner import DownloadRunner, RunnerJob
from app.models.task import Task, TaskStatus
from app.services.download_errors import user_message_for
from app.services.storage_registry import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _secret() -> str:
    return (
        (settings.DOWNLOADER_HMAC_SECRET or "").strip()
        or (settings.CLIPZI_WORKER_TOKEN or "").strip()
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_job_token(job: RunnerJob) -> str:
    """Token one-time untuk workflow (context + callback)."""
    payload = {
        "job_id": str(job.id),
        "task_id": str(job.task_id),
        "exp": int(time.time()) + max(60, settings.DOWNLOADER_JOB_TOKEN_TTL),
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_job_token(token: str) -> Dict[str, Any]:
    if not token or "." not in token:
        raise ValueError("Token job tidak valid")
    body, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret().encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Signature token job tidak valid")
    payload = json.loads(_unb64(body))
    if int(payload.get("exp") or 0) < int(time.time()):
        raise ValueError("Token job kedaluwarsa")
    return payload


def serialize_runner(runner: DownloadRunner) -> Dict[str, Any]:
    """Representasi aman untuk UI (tanpa token/private key)."""
    return {
        "id": str(runner.id),
        "name": runner.name,
        "runner_type": runner.runner_type,
        "owner": runner.owner,
        "repo": runner.repo,
        "workflow_file": runner.workflow_file,
        "git_ref": runner.git_ref,
        "auth_mode": runner.auth_mode,
        "has_token": bool(runner.token_encrypted),
        "enabled": runner.enabled,
        "status": runner.status,
        "weight": runner.weight,
        "cooldown_until": runner.cooldown_until.isoformat() if runner.cooldown_until else None,
        "success_count": runner.success_count,
        "failure_count": runner.failure_count,
        "last_execution_at": runner.last_execution_at.isoformat()
        if runner.last_execution_at
        else None,
        "last_error": runner.last_error,
        "rate_limit_remaining": runner.rate_limit_remaining,
        "rate_limit_reset_at": runner.rate_limit_reset_at.isoformat()
        if runner.rate_limit_reset_at
        else None,
    }



async def list_runners(db: AsyncSession) -> List[DownloadRunner]:
    return list(
        (await db.execute(select(DownloadRunner).order_by(DownloadRunner.created_at)))
        .scalars()
        .all()
    )


async def create_runner(db: AsyncSession, payload: Dict[str, Any]) -> DownloadRunner:
    token = str(payload.pop("token", "") or "").strip()
    runner = DownloadRunner(
        name=str(payload["name"]).strip()[:80],
        owner=str(payload["owner"]).strip()[:120],
        repo=str(payload["repo"]).strip()[:120],
        workflow_file=str(payload.get("workflow_file") or "downloader_video.yml")[:160],
        git_ref=str(payload.get("git_ref") or "main")[:80],
        auth_mode=str(payload.get("auth_mode") or "pat")[:10],
        weight=int(payload.get("weight") or 100),
        enabled=bool(payload.get("enabled", True)),
        token_encrypted=encrypt_field(token) if token else None,
    )
    db.add(runner)
    await db.commit()
    await db.refresh(runner)
    return runner


async def update_runner(
    db: AsyncSession, runner: DownloadRunner, payload: Dict[str, Any]
) -> DownloadRunner:
    token = payload.pop("token", None)
    for field in ("name", "owner", "repo", "workflow_file", "git_ref", "auth_mode", "status"):
        if payload.get(field) is not None:
            setattr(runner, field, str(payload[field])[:160])
    if payload.get("weight") is not None:
        runner.weight = max(1, int(payload["weight"]))
    if payload.get("enabled") is not None:
        runner.enabled = bool(payload["enabled"])
    if token:
        runner.token_encrypted = encrypt_field(str(token).strip())
    runner.updated_at = _now()
    await db.commit()
    await db.refresh(runner)
    return runner


def _decrypt_token(runner: DownloadRunner) -> str:
    if not runner.token_encrypted:
        raise RuntimeError("Runner belum memiliki GitHub token.")
    return decrypt_field(runner.token_encrypted)


def _github_headers(runner: DownloadRunner) -> Dict[str, str]:
    if runner.auth_mode != "pat":
        raise RuntimeError(
            "auth_mode ini belum didukung dispatcher. Gunakan PAT fine-grained "
            "(Actions: write) pada repo yang diotorisasi."
        )
    return {
        "Authorization": f"Bearer {_decrypt_token(runner)}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def check_runner(db: AsyncSession, runner: DownloadRunner) -> Dict[str, Any]:
    """Health check ringan: akses repo + rate limit GitHub."""
    base = settings.GITHUB_API_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"{base}/repos/{runner.owner}/{runner.repo}", headers=_github_headers(runner)
            )
            rate = await client.get(f"{base}/rate_limit", headers=_github_headers(runner))
        ok = response.status_code == 200
        if rate.status_code == 200:
            core = (rate.json().get("resources") or {}).get("core") or {}
            runner.rate_limit_remaining = core.get("remaining")
            reset = core.get("reset")
            runner.rate_limit_reset_at = (
                datetime.fromtimestamp(reset, tz=timezone.utc) if reset else None
            )
        runner.status = "active" if ok else "error"
        runner.last_error = None if ok else response.text[:400]
        await db.commit()
        return {"ok": ok, "status_code": response.status_code, "error": runner.last_error}
    except Exception as exc:  # jaringan / token salah
        runner.status = "error"
        runner.last_error = str(exc)[:400]
        await db.commit()
        return {"ok": False, "status_code": None, "error": runner.last_error}


async def _select_runner(
    db: AsyncSession, exclude: Optional[set[str]] = None
) -> Optional[DownloadRunner]:
    rows = (
        await db.execute(select(DownloadRunner).where(DownloadRunner.enabled.is_(True)))
    ).scalars().all()
    now = _now()
    candidates: List[DownloadRunner] = []
    weights: List[float] = []
    for runner in rows:
        if exclude and str(runner.id) in exclude:
            continue
        if runner.status == "disabled":
            continue
        if runner.status == "error":
            # Biarkan admin menjalankan Test koneksi dulu; jangan pakai runner
            # yang diketahui bermasalah.
            continue
        if runner.cooldown_until and runner.cooldown_until > now:
            continue
        total = (runner.success_count or 0) + (runner.failure_count or 0)
        success_rate = ((runner.success_count or 0) / total) if total else 0.75
        weight = max(1, runner.weight or 1) * max(0.05, success_rate)
        candidates.append(runner)
        weights.append(weight)
    if not candidates:
        return None
    return random.choices(candidates, weights=weights, k=1)[0]


def _callback_url() -> str:
    base = (settings.DOWNLOADER_CALLBACK_BASE_URL or "").strip().rstrip("/")
    if not base:
        raw = (settings.CLIPZI_CALLBACK_URL or "").strip()
        if "/api/" in raw:
            base = raw.split("/api/")[0].rstrip("/")
    return base + "/api/internal/downloader/callback" if base else ""


async def _dispatch_workflow(
    db: AsyncSession, runner: DownloadRunner, task: Task, job: RunnerJob
) -> None:
    token = issue_job_token(job)
    callback = _callback_url()
    if not callback:
        raise RuntimeError("DOWNLOADER_CALLBACK_BASE_URL / CLIPZI_CALLBACK_URL belum diisi.")
    payload = {
        "ref": runner.git_ref or "main",
        "inputs": {
            "task_id": str(task.id),
            "video_url": task.source_url,
            "callback_url": callback,
            "job_token": token,
        },
    }
    url = (
        f"{settings.GITHUB_API_URL.rstrip('/')}/repos/{runner.owner}/{runner.repo}"
        f"/actions/workflows/{runner.workflow_file}/dispatches"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=_github_headers(runner), json=payload)
    if response.status_code not in (201, 204):
        raise RuntimeError(
            f"GitHub dispatch gagal ({response.status_code}): {response.text[:300]}"
        )
    job.dispatch_id = response.headers.get("x-github-request-id") or None
    runner.last_execution_at = _now()
    await db.commit()



async def request_fallback(db: AsyncSession, task: Task) -> Dict[str, Any]:
    """Pilih runner & dispatch workflow; failover bila dispatch gagal."""
    if not settings.RUNNER_FALLBACK_ENABLED or not _secret():
        return {"queued": False, "error": "Runner fallback tidak dikonfigurasi."}

    tried: set[str] = set()
    last_error = ""
    for _ in range(5):
        runner = await _select_runner(db, exclude=tried)
        if not runner:
            break
        tried.add(str(runner.id))
        job = RunnerJob(task_id=task.id, runner_id=runner.id, status="dispatched")
        db.add(job)
        await db.commit()
        await db.refresh(job)
        try:
            await _dispatch_workflow(db, runner, task, job)
            task.download_status = "downloading"
            task.status = TaskStatus.QUEUED
            await db.commit()
            logger.info("Fallback runner %s dipakai untuk task %s", runner.name, task.id)
            return {"queued": True, "runner": runner.name, "job_id": str(job.id)}
        except Exception as exc:
            last_error = str(exc)
            job.status = "dispatch_failed"
            job.error = last_error[:800]
            runner.failure_count = (runner.failure_count or 0) + 1
            runner.last_error = last_error[:400]
            runner.cooldown_until = _now() + timedelta(minutes=5)
            await db.commit()
            logger.warning("Runner %s gagal dispatch: %s", runner.name, last_error)

    return {"queued": False, "error": last_error or "Tidak ada runner sehat."}


async def job_context(db: AsyncSession, token: str) -> Dict[str, Any]:
    """Ambil cookies + presigned upload untuk workflow (one-time)."""
    from app.services import cookie_store

    payload = verify_job_token(token)
    job = await db.get(RunnerJob, UUID(payload["job_id"]))
    if not job or job.status not in ("dispatched", "context"):
        raise ValueError("Job tidak ditemukan / token sudah dipakai.")
    task = await db.get(Task, job.task_id)
    if not task:
        raise ValueError("Task tidak ditemukan.")

    acquired = await cookie_store.acquire(db)
    cookie_text = ""
    cookie_id = None
    if acquired:
        cookie, path = acquired
        cookie_id = str(cookie.id)
        try:
            cookie_text = open(path, "r", encoding="utf-8", errors="replace").read()
        except OSError:
            cookie_text = ""
    if not cookie_text:
        # Pool kosong: pakai cookies ENV (base64) supaya runner tidak download
        # tanpa autentikasi (yang berujung bot-check).
        try:
            from app.services.downloader import VideoDownloader

            env_path = VideoDownloader()._resolve_cookiefile(None)
            if env_path:
                cookie_text = open(env_path, "r", encoding="utf-8", errors="replace").read()
                cookie_id = "env"
        except Exception as exc:
            logger.warning("Gagal memuat cookies ENV untuk runner: %s", exc)

    storage = get_storage()
    object_key = f"downloads/{task.id}/source.mp4"
    upload_url = storage.presign_put(
        object_key, "video/mp4", expiration=max(3600, settings.DOWNLOADER_JOB_TOKEN_TTL * 4)
    )
    job.status = "context"
    await db.commit()
    return {
        "task_id": str(task.id),
        "video_url": task.source_url,
        "cookie_id": cookie_id,
        "cookies": cookie_text,
        "upload_url": upload_url,
        "object_key": object_key,
        "max_file_mb": settings.DOWNLOADER_MAX_FILE_MB,
    }


async def handle_callback(
    db: AsyncSession, token: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Callback idempotent dari workflow setelah upload selesai/gagal."""
    from app.models.task_asset import TaskAsset
    from app.services.vast_worker import submit_task

    data = verify_job_token(token)
    job = await db.get(RunnerJob, UUID(data["job_id"]))
    if not job:
        raise ValueError("Job tidak ditemukan.")
    task = await db.get(Task, job.task_id)
    if not task:
        raise ValueError("Task tidak ditemukan.")
    if str(task.id) != str(data.get("task_id")):
        raise ValueError("Token job tidak cocok dengan task.")

    if job.status == "completed":
        return {"ok": True, "duplicate": True, "queued": False}

    runner = await db.get(DownloadRunner, job.runner_id) if job.runner_id else None
    status_value = str(payload.get("status") or "completed").lower()

    if status_value != "completed":
        # Kegagalan runner → cooldown + coba runner berikutnya.
        job.status = "failed"
        job.error = str(payload.get("error") or "")[:2000]
        job.finished_at = _now()
        from app.models.download_log import DownloadAttempt

        db.add(
            DownloadAttempt(
                task_id=task.id,
                user_id=task.user_id,
                attempt_no=1,
                runner_type="github",
                runner_id=str(job.runner_id) if job.runner_id else None,
                error_category=str(payload.get("error_category") or "unknown")[:40],
                error_message=str(payload.get("error") or "")[:8000],
            )
        )
        if runner:
            runner.failure_count = (runner.failure_count or 0) + 1
            runner.last_error = job.error[:400]
            runner.cooldown_until = _now() + timedelta(minutes=10)
        await db.commit()

        fallback = await request_fallback(db, task)
        if fallback.get("queued"):
            return {"ok": True, "failover": True, "queued": True}
        task.status = TaskStatus.ERROR
        task.download_status = "download_failed"
        task.user_message = user_message_for(payload.get("error_category"))
        task.error_category = str(payload.get("error_category") or "unknown")
        await db.commit()
        return {"ok": True, "failover": False, "queued": False}

    object_key = str(payload.get("object_key") or "").strip()
    url = str(payload.get("url") or "").strip()
    if not url and object_key:
        # Presigned GET agar worker tetap bisa mengunduh walau bucket privat.
        url = get_storage().get_presigned_url(object_key, expiration=86400) or get_storage().get_public_url(object_key)
    if not url:
        raise ValueError("Payload callback tidak memiliki URL/objek hasil upload.")

    task.source_asset_url = url
    task.download_status = "downloaded"
    task.status = TaskStatus.QUEUED
    task.progress = 0
    task.error_message = None
    task.user_message = None
    task.error_category = None
    if object_key:
        db.add(
            TaskAsset(
                task_id=task.id,
                storage_key=object_key,
                kind="source",
                size_bytes=payload.get("size_bytes"),
            )
        )
    job.status = "completed"
    job.finished_at = _now()
    if runner:
        runner.success_count = (runner.success_count or 0) + 1
        runner.last_error = None
    await db.commit()

    dispatch = await submit_task(task.id)
    return {"ok": True, "queued": bool(dispatch.get("queued")), "duplicate": False}

