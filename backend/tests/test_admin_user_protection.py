"""Unit test proteksi akun admin pada admin users API."""
import pytest
from fastapi import HTTPException

from app.api.admin import deps as admin_deps
from app.api.admin import users as admin_users
from app.models.user import User
from uuid import uuid4


def _user(email: str, name: str = "User") -> User:
    return User(id=uuid4(), email=email, name=name)


def test_admin_email_cannot_be_modified(monkeypatch):
    monkeypatch.setattr(admin_deps.settings, "ADMIN_EMAILS", "owner@clipzy.ai", raising=False)
    monkeypatch.setattr(
        admin_users, "is_admin_email", lambda email: (email or "").lower() == "owner@clipzy.ai"
    )
    actor = _user("other-admin@clipzy.ai")
    target = _user("owner@clipzy.ai")
    with pytest.raises(HTTPException) as exc:
        admin_users._ensure_mutable(target, actor)
    assert exc.value.status_code == 403


def test_cannot_modify_self(monkeypatch):
    monkeypatch.setattr(admin_users, "is_admin_email", lambda email: False)
    actor = _user("admin@clipzy.ai")
    with pytest.raises(HTTPException):
        admin_users._ensure_mutable(actor, actor)


def test_normal_user_can_be_modified(monkeypatch):
    monkeypatch.setattr(admin_users, "is_admin_email", lambda email: False)
    actor = _user("admin@clipzy.ai")
    target = _user("user@example.com")
    admin_users._ensure_mutable(target, actor)  # tidak raise
