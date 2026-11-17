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
    # Jenis email yang diuji (memakai template-nya). Default: notify.
    kind: Optional[str] = None


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
    kind = str(payload.kind or "notify")
    result = await mailer.send_test(db, payload.to, kind)
    _audit(
        db,
        request,
        current_admin,
        "smtp_test_sent",
        {"to": payload.to, "kind": kind, "result": result},
    )
    await db.commit()
    log_text = "\n".join(
        [
            f"SMTP test  : {'OK' if not result.get('error') else 'GAGAL'}",
            f"Ke         : {payload.to}",
            f"Jenis email: {kind}",
            f"Subjek     : {result.get('subject') or '-'}",
            f"Terkirim   : {result.get('sent', 0)}",
            f"Skip       : {result.get('skipped') or '-'}",
            f"Error      : {result.get('error') or '-'}",
        ]
    )
    if result.get("error"):
        raise HTTPException(status_code=502, detail={"message": result["error"], "log_text": log_text})
    return {**result, "log_text": log_text}


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


# ---------------------------------------------------------------------------
# Email templates (tab "Email Template" di halaman SMTP)
# ---------------------------------------------------------------------------


@router.get("/templates")
async def read_templates(db: AsyncSession = Depends(get_db_session)):
    """Daftar template efektif per jenis email + variabel yang didukung."""
    config = await mailer.get_config(db)
    return {
        "kinds": list(mailer.KINDS),
        "templates": config.get("templates") or {},
        "defaults": mailer.DEFAULT_TEMPLATES,
        "variables": mailer.TEMPLATE_VARIABLES,
    }


class TemplateIn(BaseModel):
    kind: str
    subject: Optional[str] = None
    html: Optional[str] = None
    templates: Optional[dict] = None
    ctx: Optional[dict] = None


@router.put("/templates")
async def save_templates(
    payload: TemplateIn,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Simpan subject/HTML kustom untuk satu atau beberapa jenis email."""
    if payload.templates is not None:
        config = await mailer.save_config(db, {"templates": payload.templates})
        kinds = list(payload.templates.keys())
    else:
        kind = str(payload.kind or "").strip()
        if kind not in mailer.KINDS:
            raise HTTPException(status_code=400, detail=f"Jenis email tidak dikenal: {kind}")
        config = await mailer.save_config(
            db, {"templates": {kind: {"subject": payload.subject, "html": payload.html}}}
        )
        kinds = [kind]
    _audit(db, request, current_admin, "smtp_template_updated", {"kinds": kinds})
    await db.commit()
    return {"ok": True, "kinds": kinds, "templates": config.get("templates")}


@router.post("/templates/{kind}/reset")
async def reset_template(
    kind: str,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Kembalikan satu template ke default bawaan."""
    if kind not in mailer.KINDS:
        raise HTTPException(status_code=400, detail=f"Jenis email tidak dikenal: {kind}")
    current = await mailer.get_config(db)
    stored = dict(current.get("templates") or {})
    stored.pop(kind, None)
    # Simpan ulang seluruh template efektif agar override benar-benar hilang.
    config = await mailer.save_config(
        db,
        {
            "templates": {
                k: {"subject": v.get("subject", ""), "html": v.get("html", "")}
                for k, v in stored.items()
                if k != kind
            }
        },
    )
    _audit(db, request, current_admin, "smtp_template_reset", {"kind": kind})
    await db.commit()
    return {"ok": True, "kind": kind, "templates": config.get("templates")}


@router.post("/templates/{kind}/preview")
async def preview_template(
    kind: str,
    payload: TemplateIn,
    db: AsyncSession = Depends(get_db_session),
):
    """Render pratinjau (tanpa mengirim) memakai template tersimpan."""
    config = await mailer.get_config(db)
    templates = dict(config.get("templates") or {})
    if payload.subject is not None or payload.html is not None:
        templates[kind] = {
            "subject": payload.subject or templates.get(kind, {}).get("subject", ""),
            "html": payload.html or templates.get(kind, {}).get("html", ""),
        }
    return mailer.preview(kind, payload.ctx or None, templates)
