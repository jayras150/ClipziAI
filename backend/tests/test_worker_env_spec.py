"""Regresi: tampilan env admin harus jujur soal cookies terkompresi.

Cookies yang terlalu besar dikirim sebagai `YTDLP_COOKIES_GZIP_B64`; dulu
`worker_env_spec()` hanya memeriksa `YTDLP_COOKIES_BASE64` sehingga tab
Environment menampilkan "kosong" padahal cookies ada.
"""
from app.services import vast_admin as va


def _patch_env(monkeypatch, env):
    monkeypatch.setattr(va, "build_worker_env", lambda task_id=None: dict(env))


def test_cookies_gzip_tampil_ada(monkeypatch):
    packed = "QUJD" * 20
    _patch_env(
        monkeypatch,
        {
            "CLIPZI_ROLE": "worker",
            "YTDLP_COOKIES_GZIP_B64": packed,
            "HF_TOKEN": "hf_x",
        },
    )

    items = {row["name"]: row for row in va.worker_env_spec()}

    assert items["YTDLP_COOKIES_BASE64"]["set"] is True
    assert "gzip" in str(items["YTDLP_COOKIES_BASE64"]["preview"])
    assert items["HF_TOKEN"]["set"] is True


def test_env_text_mengekspor_gzip_bukan_base64(monkeypatch):
    _patch_env(
        monkeypatch,
        {
            "CLIPZI_ROLE": "worker",
            "YTDLP_COOKIES_GZIP_B64": "QUJD",
        },
    )

    text = va.env_text(reveal=True)

    assert "YTDLP_COOKIES_GZIP_B64=QUJD" in text
    assert "YTDLP_COOKIES_BASE64=" not in text


def test_env_text_secret_disamarkan(monkeypatch):
    _patch_env(
        monkeypatch,
        {
            "CLIPZI_ROLE": "worker",
            "HF_TOKEN": "hf_secret_value",
        },
    )

    text = va.env_text(reveal=False)

    assert "hf_secret_value" not in text
    assert "HF_TOKEN=****" in text
