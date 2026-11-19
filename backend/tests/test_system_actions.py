"""Regresi: POST /api/admin/system/actions harus benar-benar mengantrekan job.

Bug asli: handler memakai variabel `args` yang tidak pernah didefinisikan →
`NameError: name 'args' is not defined` → HTTP 500 → tombol Clear Cache /
Restart Caddy / Prune Docker di dashboard selalu gagal.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.api.admin.system import run_system_action


def test_aksi_tanpa_args_mengantrekan_job():
    result = asyncio.run(run_system_action({"action": "clear_cache"}))

    assert result["ok"] is True
    job = result["job"]
    assert job["action"] == "clear_cache"
    assert job["status"] == "pending"
    assert job["args"] == []


def test_aksi_dengan_args_diteruskan():
    result = asyncio.run(
        run_system_action({"action": "backup_now", "args": ["--label", "manual"]})
    )

    assert result["job"]["args"] == ["--label", "manual"]


def test_aksi_tidak_dikenal_ditolak_400():
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(run_system_action({"action": "rm_rf_root"}))

    assert excinfo.value.status_code == 400
