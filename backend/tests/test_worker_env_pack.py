"""Tes pemadatan env worker (batas ~4 KB Vast)."""
import base64
import gzip

from app.services import vast_worker


def _env_with_big_cookies(size: int = 5000) -> dict:
    return {
        "CLIPZI_ROLE": "worker",
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "YTDLP_COOKIES_BASE64": "QUJD" * (size // 4),
    }


def test_env_besar_dipadatkan_jadi_gzip():
    env = vast_worker._pack_worker_env(_env_with_big_cookies())
    assert "YTDLP_COOKIES_BASE64" not in env
    packed = env["YTDLP_COOKIES_GZIP_B64"]
    assert len(packed) < 5000
    total = sum(len(str(key)) + len(str(value)) for key, value in env.items())
    assert total < 4000
    raw = gzip.decompress(base64.b64decode(packed.encode("ascii"))).decode("utf-8")
    assert raw.startswith("QUJD")


def test_env_kecil_tidak_diubah():
    env = {"CLIPZI_ROLE": "worker", "YTDLP_COOKIES_BASE64": "QUJD"}
    assert vast_worker._pack_worker_env(env) == env


def test_env_tanpa_cookies_aman():
    env = {"CLIPZI_ROLE": "worker"}
    assert vast_worker._pack_worker_env(env) == env
