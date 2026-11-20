"""Test pembersihan sampah server: aman secara default, hanya file aplikasi.

Yang dijaga:
  - `dry_run` tidak menghapus apa pun;
  - file milik aplikasi lain (mis. database) TIDAK pernah disentuh;
  - log besar dipotong, bukan dihapus;
  - target `docker` tidak jalan tanpa izin eksplisit.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from app.core.config import get_settings
from app.services import server_cleanup as sc


def _old_file(directory: Path, name: str, size: int = 128, age_hours: float = 48) -> Path:
    path = directory / name
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_hours * 3600
    os.utime(path, (stamp, stamp))
    return path


def test_temp_hanya_file_prefix_aplikasi(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_candidate_temp_dirs", lambda: [tmp_path])
    ours = _old_file(tmp_path, "clipzi-render.bin")
    theirs = _old_file(tmp_path, "database.sqlite")

    found = {item["path"] for item in sc.scan_temp(24)}

    assert str(ours) in found
    assert str(theirs) not in found


def test_temp_baru_tidak_dipilih(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_candidate_temp_dirs", lambda: [tmp_path])
    fresh = _old_file(tmp_path, "ytdlp_baru.bin", age_hours=0.1)

    found = {item["path"] for item in sc.scan_temp(24)}

    assert str(fresh) not in found


def test_dry_run_tidak_menghapus(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_candidate_temp_dirs", lambda: [tmp_path])
    path = _old_file(tmp_path, "ytdlp_lama.bin")

    result = asyncio.run(sc.cleanup_server(dry_run=True, targets=["temp"]))

    assert path.exists()
    assert result["freed_bytes"] == 0
    assert result["results"][0]["candidates"] == 1


def test_hapus_saat_dry_run_false(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_candidate_temp_dirs", lambda: [tmp_path])
    path = _old_file(tmp_path, "reframe_lama.bin")

    result = asyncio.run(sc.cleanup_server(dry_run=False, targets=["temp"]))

    assert not path.exists()
    assert result["freed_bytes"] > 0
    assert result["summary"]["temp"] == 1


def test_log_besar_dipotong_bukan_dihapus(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_root_dir", lambda: tmp_path)
    settings = get_settings()
    # Batas 1 MB supaya file 2 MB dianggap kebesaran.
    monkeypatch.setattr(settings, "SERVER_CLEANUP_LOG_MAX_MB", 1, raising=False)
    logs = tmp_path / "logs"
    logs.mkdir()
    big = logs / "app.log"
    big.write_bytes(b"a" * (2 * 1024 * 1024))

    result = asyncio.run(sc.cleanup_server(dry_run=False, targets=["logs"]))

    assert big.exists(), "log tidak boleh dihapus"
    assert big.stat().st_size <= 1024 * 1024
    assert result["summary"]["logs"] == 1


def test_docker_dilewati_tanpa_izin(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "SERVER_CLEANUP_DOCKER", False, raising=False)

    result = asyncio.run(sc.cleanup_server(dry_run=False, targets=["docker"]))

    assert result["results"][0].get("skipped") == "disabled"


def test_describe_tanpa_error():
    info = sc.describe()

    assert "candidates" in info
    assert set(["temp", "logs", "cache"]).issubset(info["candidates"])
    assert isinstance(info["enabled"], bool)
