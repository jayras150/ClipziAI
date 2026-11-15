"""Unit test cookie flags J9 (tanpa HTTP server)."""
from fastapi import Response

from app.core.auth_cookies import clear_auth_cookies, set_auth_cookies
from app.schemas.auth import RefreshTokenRequest


def test_auth_cookies_are_httponly_and_csrf_visible():
    response = Response()
    set_auth_cookies(response, "access-token", "refresh-token")
    cookies = response.headers.getlist("set-cookie")
    access = next(item for item in cookies if item.startswith("clipzy_access="))
    refresh = next(item for item in cookies if item.startswith("clipzy_refresh="))
    csrf = next(item for item in cookies if item.startswith("clipzy_csrf="))
    session = next(item for item in cookies if item.startswith("clipzy_session="))
    assert "HttpOnly" in access
    assert "HttpOnly" in refresh
    assert "HttpOnly" not in csrf
    assert "HttpOnly" not in session
    assert "SameSite=lax" in access


def test_clear_auth_cookies_removes_all():
    response = Response()
    clear_auth_cookies(response)
    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 4
    assert all("Max-Age=0" in item for item in cookies)


def test_refresh_request_can_use_cookie():
    assert RefreshTokenRequest().refresh_token is None
