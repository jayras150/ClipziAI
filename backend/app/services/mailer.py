"""SMTP + template email Clipzi (dipakai admin & auth flows).

Konfigurasi disimpan di `platform_settings` (key `smtp_config`) sehingga bisa
diubah dari admin tanpa restart. Password disimpan terenkripsi.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_field, encrypt_field
from app.services import platform_settings as ps

logger = logging.getLogger(__name__)

KEY = "smtp_config"
KINDS = ("welcome", "verify", "otp", "reset", "notify", "report")
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "host": "",
    "port": 587,
    "username": "",
    "password_enc": "",
    "from_email": "noreply@clipzy.ai",
    "from_name": "Clipzy AI",
    "use_tls": True,
    "use_ssl": False,
    "reply_to": "",
    "types": {kind: True for kind in KINDS},
}


async def get_config(db: AsyncSession) -> Dict[str, Any]:
    raw = await ps.get_setting(db, KEY, {})
    config = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        config.update({k: v for k, v in raw.items() if k in DEFAULT_CONFIG})
        if isinstance(raw.get("types"), dict):
            config["types"] = {**DEFAULT_CONFIG["types"], **raw["types"]}
    return config


def public_config(config: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(config)
    password = ""
    if config.get("password_enc"):
        try:
            password = decrypt_field(str(config["password_enc"]))
        except Exception:  # noqa: BLE001
            password = ""
    data.pop("password_enc", None)
    data["password_set"] = bool(password)
    data["password_preview"] = (password[:2] + "•••" + password[-2:]) if len(password) > 6 else ""
    return data


async def save_config(db: AsyncSession, payload: Dict[str, Any]) -> Dict[str, Any]:
    current = await get_config(db)
    updated = dict(current)
    for field in ("enabled", "host", "username", "from_email", "from_name", "use_tls", "use_ssl", "reply_to"):
        if field in payload:
            updated[field] = payload[field]
    if "port" in payload:
        updated["port"] = int(payload["port"] or 587)
    password = str(payload.get("password") or "").strip()
    if password:
        updated["password_enc"] = encrypt_field(password)
    if isinstance(payload.get("types"), dict):
        updated["types"] = {**current["types"], **{k: bool(v) for k, v in payload["types"].items() if k in KINDS}}
    await ps.set_setting(db, KEY, updated)
    await db.commit()
    return await get_config(db)


def _wrap(title: str, body: str, footer: str = "") -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#0b0d12;font-family:Inter,Arial,sans-serif;color:#e5e7eb">
<div style="max-width:560px;margin:0 auto;padding:28px 20px">
  <div style="text-align:center;margin-bottom:18px">
    <span style="display:inline-block;padding:10px 14px;border-radius:12px;background:linear-gradient(135deg,#f4c76b,#c98a2f);color:#1b1405;font-weight:800">Clipzy AI</span>
  </div>
  <div style="background:#11151f;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:24px">
    <h1 style="margin:0 0 12px;font-size:18px;color:#fff">{title}</h1>
    <div style="font-size:14px;line-height:1.6;color:#c7ccd8">{body}</div>
  </div>
  <p style="text-align:center;font-size:11px;color:#6b7280;margin-top:16px">{footer or 'You receive this email because you use Clipzy AI.'}</p>
</div></body></html>"""


def render(kind: str, ctx: Dict[str, Any]) -> tuple[str, str]:
    name = str(ctx.get("name") or "there")
    if kind == "welcome":
        subject = "Welcome to Clipzy AI"
        body = f"<p>Hi {name}, your Clipzy AI account is ready. Turn long videos into viral clips in minutes.</p>"
        if ctx.get("verify_url"):
            body += f'<p><a href="{ctx["verify_url"]}" style="background:#f4c76b;color:#1b1405;padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700">Verify email</a></p>'
    elif kind == "verify":
        subject = "Verify your Clipzy AI email"
        body = f'<p>Hi {name}, confirm your email to activate all features.</p><p><a href="{ctx.get("verify_url", "#")}">Verify email</a></p>'
    elif kind == "otp":
        subject = "Your Clipzy AI verification code"
        body = f'<p>Hi {name}, your one-time code is:</p><p style="font-size:28px;font-weight:800;letter-spacing:6px;color:#f4c76b">{ctx.get("code", "")}</p><p>This code expires in {ctx.get("minutes", 10)} minutes.</p>'
    elif kind == "reset":
        subject = "Reset your Clipzy AI password"
        body = f'<p>Hi {name}, reset your password using the link below (valid 30 minutes).</p><p><a href="{ctx.get("reset_url", "#")}">Reset password</a></p><p>If you did not request this, ignore this email.</p>'
    elif kind == "report":
        subject = str(ctx.get("subject") or "Clipzy AI report")
        body = str(ctx.get("html") or "")
    else:
        subject = str(ctx.get("subject") or "Clipzy AI notification")
        body = str(ctx.get("html") or "")
    return subject, _wrap(subject, body, str(ctx.get("footer") or ""))


def _send_sync(config: Dict[str, Any], recipients: Iterable[str], subject: str, html: str) -> int:
    host = str(config.get("host") or "").strip()
    if not host:
        raise RuntimeError("SMTP host belum diisi")
    port = int(config.get("port") or 587)
    username = str(config.get("username") or "").strip()
    password = ""
    if config.get("password_enc"):
        password = decrypt_field(str(config["password_enc"]))
    from_email = str(config.get("from_email") or username or "noreply@clipzy.ai")
    from_name = str(config.get("from_name") or "Clipzy AI")
    sent = 0
    context = ssl.create_default_context()
    if config.get("use_ssl"):
        client = smtplib.SMTP_SSL(host, port, context=context, timeout=25)
    else:
        client = smtplib.SMTP(host, port, timeout=25)
    try:
        client.ehlo()
        if config.get("use_tls") and not config.get("use_ssl"):
            client.starttls(context=context)
            client.ehlo()
        if username and password:
            client.login(username, password)
        for to in recipients:
            message = EmailMessage()
            message["From"] = f"{from_name} <{from_email}>"
            message["To"] = to
            message["Subject"] = subject
            if config.get("reply_to"):
                message["Reply-To"] = str(config["reply_to"])
            message.set_content("Please view this email in an HTML capable client.")
            message.add_alternative(html, subtype="html")
            client.send_message(message)
            sent += 1
    finally:
        try:
            client.quit()
        except Exception:  # noqa: BLE001
            pass
    return sent


async def send(
    db: AsyncSession,
    to: List[str],
    kind: str,
    ctx: Dict[str, Any],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    import asyncio

    config = await get_config(db)
    if not config.get("enabled") and not force:
        return {"sent": 0, "skipped": "smtp_disabled"}
    if not force and not (config.get("types") or {}).get(kind, True):
        return {"sent": 0, "skipped": f"type_{kind}_disabled"}
    recipients = [email.strip() for email in to if email and "@" in email]
    if not recipients:
        return {"sent": 0, "skipped": "no_recipients"}
    subject, html = render(kind, ctx)
    try:
        sent = await asyncio.to_thread(_send_sync, config, recipients, subject, html)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMTP gagal (%s): %s", kind, exc)
        return {"sent": 0, "error": str(exc)[:300]}
    return {"sent": sent, "subject": subject}


async def send_test(db: AsyncSession, to: str) -> Dict[str, Any]:
    return await send(db, [to], "notify", {"subject": "Clipzy AI SMTP test", "html": "<p>SMTP configuration works.</p>"}, force=True)


__all__ = ["KINDS", "get_config", "public_config", "render", "save_config", "send", "send_test"]
