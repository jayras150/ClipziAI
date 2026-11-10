"""
Konfigurasi pytest.

`app.core.config` mewajibkan SECRET_KEY & DATABASE_URL saat import, jadi env
minimal di-set SEBELUM modul app diimpor. Tidak ada koneksi DB di test ini —
semua unit test murni (tanpa I/O).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/clipzi_test"
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
