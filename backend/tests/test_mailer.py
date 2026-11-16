"""Tes mailer: katalog jenis, render template, masking password."""
from app.services import mailer


def test_kinds_lengkap():
    assert set(mailer.KINDS) == {"welcome", "verify", "otp", "reset", "notify", "report"}


def test_render_verifikasi_dan_otp():
    subject, html = mailer.render("verify", {"name": "Ada", "verify_url": "https://x/verify"})
    assert "Verify" in subject
    assert "https://x/verify" in html

    subject, html = mailer.render("otp", {"name": "Ada", "code": "123456", "minutes": 10})
    assert "code" in subject.lower()
    assert "123456" in html


def test_render_reset_dan_report():
    subject, html = mailer.render("reset", {"name": "Ada", "reset_url": "https://x/reset"})
    assert "Reset" in subject
    assert "https://x/reset" in html

    subject, html = mailer.render("report", {"subject": "Weekly", "html": "<p>stats</p>"})
    assert subject == "Weekly"
    assert "stats" in html


def test_public_config_tidak_membocorkan_password():
    config = dict(mailer.DEFAULT_CONFIG)
    config["password_enc"] = ""
    public = mailer.public_config(config)
    assert "password_enc" not in public
    assert public["password_set"] is False
    assert public["types"]["otp"] is True
