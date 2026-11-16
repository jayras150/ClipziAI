"""Admin - konfigurasi SMTP + kirim email (notifikasi & laporan)."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.audit_log import ActorType, AuditLog
from app.models.clip import Clip
from app.models.task import Task
from app.models.user import User
from app.services import mailer

router = APIRouter(dependencies=[Depends(get_current_admin)])


class SmtpIn(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: Optional[str] = None
    from_email: str = "noreply@clipzy.ai"
    from_name: str = "Clipzy AI"
    use_tls: bool = True
    use_ssl: bool = False
    reply_to: str = ""
    types: dict = {}


class TestIn(BaseModel):
    to: str


class NotifyIn(BaseModel):
    subject: str
    message: str
    emails: List[str] = []


class ReportIn(BaseModel):
    emails: List[str] = []


def _audit(db: AsyncSession, request: Request, admin: User, action: str, meta: dict) -> None:
    db.add(
        AuditLog(
            actor_type=ActorType.ADMIN,
            actor_id=admin.id,
            actor_email=admin.email,
            action=action,
            resource_type="smtp",
            meta_data=meta,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )


@router.get("")
async def read_smtp(db: AsyncSession = Depends(get_db_session)):
    config = await mailer.get_config(db)
    return {"config": mailer.public_config(config), "kinds": list(mailer.KINDS)}


@router.put("")
async def save_smtp(
    payload: SmtpIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    config = await mailer.save_config(db, payload.model_dump())
    _audit(db, request, current_admin, "smtp_config_saved", {"enabled": config.get("enabled")})
    await db.commit()
    return {"ok": True, "config": mailer.public_config(config)}


@router.post("/test")
async def test_smtp(
    payload: TestIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    result = await mailer.send_test(db, payload.to)
    _audit(db, request, current_admin, "smtp_test_sent", {"to": payload.to, "result": result})
    await db.commit()
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.post("/notify")
async def send_notification(
    payload: NotifyIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    emails = [email for email in payload.emails if email]
    if not emails:
        rows = (await db.execute(select(User.email).where(User.is_active.is_(True)).limit(500))).all()
        emails = [row[0] for row in rows]
    html = f"<p>{payload.message}</p>"
    result = await mailer.send(db, emails, "notify", {"subject": payload.subject, "html": html})
    _audit(db, request, current_admin, "smtp_notification_sent", {"count": len(emails), "result": result})
    await db.commit()
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@router.post("/report")
async def send_report(
    payload: ReportIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    users = int((await db.execute(select(func.count(User.id)))).scalar() or 0)
    tasks = int((await db.execute(select(func.count(Task.id)))).scalar() or 0)
    clips = int((await db.execute(select(func.count(Clip.id)))).scalar() or 0)
    html = (
        "<table style=\"width:100%;border-collapse:collapse\">"
        f"<tr><td>Total users</td><td style=\"text-align:right;font-weight:700\">{users}</td></tr>"
        f"<tr><td>Total tasks</td><td style=\"text-align:right;font-weight:700\">{tasks}</td></tr>"
        f"<tr><td>Total clips</td><td style=\"text-align:right;font-weight:700\">{clips}</td></tr>"
        "</table>"
    )
    emails = payload.emails or [current_admin.email]
    result = await mailer.send(
        db, emails, "report", {"subject": "Clipzy AI - platform report", "html": html}
    )
    _audit(db, request, current_admin, "smtp_report_sent", {"count": len(emails), "result": result})
    await db.commit()
    if result.get("error"):
        raise HTTPException(status_code=502, detail=result["error"])
    return result
