"""
Test sinkronisasi storage antar provider (tanpa jaringan/DB asli).

Regresi yang dijaga:
  * sync lama timeout karena berjalan di dalam request & membaca file ke RAM,
  * limit dihitung global sehingga mirror kedua tidak diproses,
  * `path_prefix` mirror diabaikan,
  * file yang hanya ada di mirror tidak pernah dipulihkan ke primary.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import pytest

from app.services import storage_registry as registry
from app.services import storage_sync


class FakeClient:
    def __init__(self, objects: Optional[Dict[str, bytes]] = None) -> None:
        self.objects: Dict[str, bytes] = dict(objects or {})
        self.content_type = "video/mp4"
        self.put_calls: List[str] = []

    def list_objects_v2(self, Bucket: str, MaxKeys: int = 1000, Prefix: str = "", **kw: Any):
        keys = [key for key in sorted(self.objects) if not Prefix or key.startswith(Prefix)]
        return {
            "Contents": [{"Key": key, "Size": len(self.objects[key])} for key in keys],
            "IsTruncated": False,
        }

    def head_object(self, Bucket: str, Key: str):
        if Key not in self.objects:
            raise Exception("404 Not Found")
        return {"ContentLength": len(self.objects[Key]), "ContentType": self.content_type}

    def get_object(self, Bucket: str, Key: str):
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str = ""):
        self.objects[Key] = Body
        self.put_calls.append(Key)
        return {"ok": True}

    def download_file(self, bucket: str, key: str, path: str):
        with open(path, "wb") as handle:
            handle.write(self.objects[key])

    def upload_file(self, path: str, bucket: str, key: str, ExtraArgs: Optional[dict] = None):
        with open(path, "rb") as handle:
            self.objects[key] = handle.read()
        self.put_calls.append(key)


def _wire(monkeypatch, config: Dict[str, Any], clients: Dict[str, FakeClient], prefixes: Dict[str, str]):
    monkeypatch.setattr(storage_sync.registry, "get_config", lambda: config)

    def fake_resolve(item: Dict[str, Any]) -> registry.ResolvedStorage:
        item_id = str(item.get("id"))
        return registry.ResolvedStorage(
            item=item,
            client=clients[item_id],
            bucket=str(item.get("bucket") or "bucket"),
            public_domain="",
            path_prefix=prefixes.get(item_id, ""),
        )

    monkeypatch.setattr(storage_sync.registry, "resolve", fake_resolve)


def _config(primary: str, mirrors: List[str]) -> Dict[str, Any]:
    ids = [primary] + mirrors
    return {
        "primary_id": primary,
        "mirror_ids": mirrors,
        "items": [
            {"id": item_id, "name": item_id, "provider": "r2", "bucket": item_id, "enabled": True}
            for item_id in ids
        ],
    }


def test_push_menyalin_dan_menghormati_prefix(monkeypatch):
    primary = FakeClient({"clips/a.mp4": b"a" * 10, "clips/b.mp4": b"b" * 10})
    mirror = FakeClient()
    _wire(monkeypatch, _config("p", ["m"]), {"p": primary, "m": mirror}, {"m": "backup"})

    storage_sync._run("push", limit=10, max_size_bytes=1024)

    assert "backup/clips/a.mp4" in mirror.objects
    assert "backup/clips/b.mp4" in mirror.objects
    status = storage_sync.job_status()
    assert status["state"] == "done"
    assert status["copied"] == 2
    assert status["failed"] == 0


def test_limit_dihitung_per_mirror(monkeypatch):
    """Bug lama: limit global membuat mirror kedua tidak memproses apa pun."""
    primary = FakeClient({"a.txt": b"1", "b.txt": b"2"})
    m1, m2 = FakeClient(), FakeClient()
    _wire(
        monkeypatch,
        _config("p", ["m1", "m2"]),
        {"p": primary, "m1": m1, "m2": m2},
        {},
    )

    storage_sync._run("push", limit=1, max_size_bytes=1024)

    assert len(m1.objects) == 1
    assert len(m2.objects) == 1


def test_reconcile_memulihkan_primary_dari_mirror(monkeypatch):
    primary = FakeClient({"a.txt": b"1"})
    mirror = FakeClient({"a.txt": b"1", "hilang.txt": b"backup"})
    _wire(monkeypatch, _config("p", ["m"]), {"p": primary, "m": mirror}, {})

    storage_sync._run("reconcile", limit=10, max_size_bytes=1024)

    assert "hilang.txt" in primary.objects
    assert primary.objects["hilang.txt"] == b"backup"


def test_heal_tidak_menulis_ke_mirror(monkeypatch):
    primary = FakeClient({})
    mirror = FakeClient({"x.txt": b"x"})
    _wire(monkeypatch, _config("p", ["m"]), {"p": primary, "m": mirror}, {})

    storage_sync._run("heal", limit=10, max_size_bytes=1024)

    assert primary.objects.get("x.txt") == b"x"
    assert mirror.put_calls == []


def test_skip_objek_terlalu_besar(monkeypatch):
    primary = FakeClient({"big.bin": b"0" * 2048})
    mirror = FakeClient()
    _wire(monkeypatch, _config("p", ["m"]), {"p": primary, "m": mirror}, {})

    storage_sync._run("push", limit=10, max_size_bytes=100)

    assert mirror.objects == {}
    assert storage_sync.job_status()["skipped"] == 1


def test_locate_menemukan_di_semua_provider(monkeypatch):
    primary = FakeClient({"clips/a.mp4": b"a"})
    mirror = FakeClient({"backup/clips/a.mp4": b"a"})
    _wire(monkeypatch, _config("p", ["m"]), {"p": primary, "m": mirror}, {"m": "backup"})

    result = storage_sync.locate("clips/a.mp4")

    assert result["found"] == 2
    assert {row["id"] for row in result["locations"]} == {"p", "m"}


def test_start_sync_menolak_tanpa_konfigurasi(monkeypatch):
    monkeypatch.setattr(storage_sync.registry, "get_config", lambda: {"items": []})
    monkeypatch.setattr(storage_sync, "_thread", None)

    result = storage_sync.start_sync()

    assert result["started"] is False
    assert "belum dikonfigurasi" in result["message"]
