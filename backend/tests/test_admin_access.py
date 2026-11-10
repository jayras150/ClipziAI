"""Unit test gerbang admin berbasis email (ADMIN_EMAILS)."""
from app.api.admin.deps import admin_emails, is_admin_email
from app.core.config import get_settings


def test_parsing_email_admin(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", " Owner@Clipzy.ai , partner@gmail.com ,, ", raising=False)
    assert admin_emails() == {"owner@clipzy.ai", "partner@gmail.com"}
    assert is_admin_email("OWNER@clipzy.ai") is True
    assert is_admin_email("partner@gmail.com") is True
    assert is_admin_email("random@user.com") is False
    assert is_admin_email(None) is False


def test_kosong_berarti_tidak_ada_admin(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "", raising=False)
    assert admin_emails() == set()
    assert is_admin_email("siapa@saja.com") is False
