"""Tes pemadatan env worker (batas ~4 KB Vast)."""
import base64
import gzip

from app.services import vast_worker


def _cookie_b64(size: int) -> str:
    """Base64 dari teks cookies Netscape yang realistis (banyak baris mirip)."""
    lines = [
        ".youtube.com\tTRUE\t/\tTRUE\t1799999999\tSID\t" + "a" * 60
        for _ in range(max(1, size // 90))
    ]
    raw = ("# Netscape HTTP Cookie File\n" + "\n".join(lines)).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def test_env_besar_dipadatkan_jadi_gzip():
    cookies = _cookie_b64(6000)
    env = {
        "CLIPZI_ROLE": "worker",
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "YTDLP_COOKIES_BASE64": cookies,
    }
    packed_env = vast_worker._pack_worker_env(dict(env))
    total = sum(len(str(key)) + len(str(value)) for key, value in packed_env.items())
    assert total < 4000
    assert "YTDLP_COOKIES_BASE64" not in packed_env
    # Kalau masih terlalu besar, cookies dibuang agar instance tetap bisa dibuat.
    if "YTDLP_COOKIES_GZIP_B64" in packed_env:
        raw = gzip.decompress(base64.b64decode(packed_env["YTDLP_COOKIES_GZIP_B64"]))
        assert base64.b64encode(raw).decode("ascii") == cookies
    else:
        assert packed_env["YTDLP_COOKIES_MISSING"] == "1"


def test_env_kecil_tidak_diubah():
    env = {"CLIPZI_ROLE": "worker", "YTDLP_COOKIES_BASE64": "QUJD"}
    assert vast_worker._pack_worker_env(dict(env)) == env


def test_env_tanpa_cookies_aman():
    env = {"CLIPZI_ROLE": "worker"}
    assert vast_worker._pack_worker_env(dict(env)) == env
