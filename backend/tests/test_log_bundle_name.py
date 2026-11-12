"""Nama bundle log harus memuat task_id dan instance_id."""
from app.services import log_bundle


def test_suffix_instance_dari_env(monkeypatch):
    monkeypatch.setenv("WORKER_INSTANCE_ID", "60315038")
    assert log_bundle._instance_suffix() == "_60315038"


def test_suffix_dari_container_label(monkeypatch):
    monkeypatch.delenv("WORKER_INSTANCE_ID", raising=False)
    monkeypatch.setenv("VAST_CONTAINERLABEL", "abc:60315038")
    assert log_bundle._instance_suffix() == "_60315038"


def test_suffix_kosong_tanpa_instance(monkeypatch):
    monkeypatch.delenv("WORKER_INSTANCE_ID", raising=False)
    monkeypatch.delenv("VAST_CONTAINERLABEL", raising=False)
    assert log_bundle._instance_suffix() == ""
