"""Cookie helpers for the user session (J9)."""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE = "clipzy_access"
REFRESH_COOKIE = "clipzy_refresh"
CSRF_COOKIE = "clipzy_csrf"
SESSION_COOKIE = "clipzy_session"
CSRF_HEADER = "X-CSRF-Token"


def _cookie_kwargs() -> dict:
    settings = get_settings()
    return {
        "secure": bool(getattr(settings, "COOKIE_SECURE", True)),
        "samesite": "lax",
        "path": "/",
        "domain": getattr(settings, "COOKIE_DOMAIN", None) or None,
    }


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    *,
    csrf_token: Optional[str] = None,
) -> str:
    settings = get_settings()
    csrf = csrf_token or secrets.token_urlsafe(32)
    kwargs = _cookie_kwargs()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        httponly=True,
        max_age=max(60, int(settings.ACCESS_TOKEN_MINUTES) * 60),
        **kwargs,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        max_age=max(3600, int(settings.REFRESH_TOKEN_DAYS) * 86400),
        **kwargs,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        max_age=max(3600, int(settings.REFRESH_TOKEN_DAYS) * 86400),
        **kwargs,
    )
    response.set_cookie(
        SESSION_COOKIE,
        "1",
        httponly=False,
        max_age=max(3600, int(settings.REFRESH_TOKEN_DAYS) * 86400),
        **kwargs,
    )
    return csrf


def clear_auth_cookies(response: Response) -> None:
    kwargs = _cookie_kwargs()
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE, SESSION_COOKIE):
        response.delete_cookie(name, path="/", domain=kwargs["domain"], secure=kwargs["secure"], samesite="lax")


__all__ = [
    "ACCESS_COOKIE",
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "REFRESH_COOKIE",
    "SESSION_COOKIE",
    "clear_auth_cookies",
    "set_auth_cookies",
]
