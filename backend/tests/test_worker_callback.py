"""Unit test helper callback worker (tanpa jaringan)."""
from __future__ import annotations

from app.services.worker_callback import instance_id_from_env


def test_instance_id_dari_vast_containerlabel(monkeypatch):
    monkeypatch.delenv("CLIPZI_INSTANCE_ID", raising=False)
    monkeypatch.delenv("CONTAINER_ID", raising=False)
    monkeypatch.setenv("VAST_CONTAINERLABEL", "C.60248471")
    assert instance_id_from_env() == 60248471


def test_instance_id_prioritas_env_eksplisit(monkeypatch):
    monkeypatch.setenv("VAST_CONTAINERLABEL", "C.111")
    monkeypatch.setenv("CLIPZI_INSTANCE_ID", "222")
    assert instance_id_from_env() == 222


def test_instance_id_none_bila_tidak_ada(monkeypatch):
    for key in ("CLIPZI_INSTANCE_ID", "VAST_CONTAINERLABEL", "CONTAINER_ID"):
        monkeypatch.delenv(key, raising=False)
    assert instance_id_from_env() is None
