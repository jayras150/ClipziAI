"""
Sinkronisasi objek antar provider storage (primary ↔ mirror).

Kenapa file ini ada: `sync_mirrors()` versi lama berjalan **di dalam satu request
HTTP** dan membaca setiap objek ke RAM (`Body.read()`). Untuk klip 60 MB lewat
Cloudflare/Node, request tersebut timeout (`HeadersTimeoutError`) dan container
API kehabisan memori. Sekarang sync adalah **job background** dengan progres yang
bisa dipantau, streaming ke file sementara, dan dukungan dua arah.

Mode:
  * ``push``      — primary → mirror (hanya objek yang belum ada di mirror).
  * ``reconcile`` — dua arah; file yang hanya ada di mirror disalin balik ke
                    primary, file baru di primary disalin ke mirror.
  * ``heal``      — khusus memulihkan primary dari mirror (tanpa menulis ke mirror).
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.services import storage_registry as registry

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50          # objek per mirror per job (aman untuk bandwidth VPS)
MAX_LIMIT = 500
DEFAULT_MAX_SIZE_MB = 500   # lewati objek raksasa agar tidak menghabiskan disk
SMALL_OBJECT_BYTES = 8 * 1024 * 1024   # <= 8 MB: pakai memori
RETRY_ATTEMPTS = 3

_job: Dict[str, Any] = {
    "state": "idle",
    "mode": "push",
    "started_at": None,
    "finished_at": None,
    "per_mirror": [],
    "total": 0,
    "done": 0,
    "copied": 0,
    "skipped": 0,
    "failed": 0,
    "bytes": 0,
    "current": "",
    "error": None,
}
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_cancel = threading.Event()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update(**fields: Any) -> None:
    with _lock:
        _job.update(fields)


def _bump(mirror_id: str, **deltas: int) -> None:
    """Naikkan penghitung job dan mirror secara atomik."""
    with _lock:
        for key, value in deltas.items():
            _job[key] = int(_job.get(key) or 0) + value
        for row in _job.get("per_mirror", []):
            if row.get("id") == mirror_id:
                for key, value in deltas.items():
                    row[key] = int(row.get(key) or 0) + value
                break


def job_status() -> Dict[str, Any]:
    with _lock:
        return {**_job, "per_mirror": [dict(row) for row in _job.get("per_mirror", [])]}


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def _resolve_pair() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    config = registry.get_config()
    if not config.get("items"):
        raise RuntimeError("storage belum dimuat (konfigurasi kosong)")
    primary_id = config.get("primary_id")
    primary = next((i for i in config["items"] if i.get("id") == primary_id), None)
    if primary is None:
        primary = next((i for i in config["items"] if i.get("enabled", True)), None)
    if primary is None:
        raise RuntimeError("primary storage belum diset")
    mirrors = [
        i
        for i in config["items"]
        if i.get("id") in (config.get("mirror_ids") or []) and i.get("id") != primary["id"]
    ]
    return primary, mirrors


def _list_keys(resolved: registry.ResolvedStorage) -> List[Dict[str, Any]]:
    """Semua objek pada satu provider (key penuh + ukuran)."""
    out: List[Dict[str, Any]] = []
    token: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": resolved.bucket, "MaxKeys": 1000}
        if resolved.path_prefix:
            kwargs["Prefix"] = resolved.path_prefix
        if token:
            kwargs["ContinuationToken"] = token
        page = resolved.client.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            key = obj.get("Key") or ""
            if not key or key.endswith("/"):
                continue
            out.append({"key": key, "size": int(obj.get("Size") or 0)})
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return out


def _relative_key(resolved: registry.ResolvedStorage, key: str) -> str:
    """Buang path_prefix provider supaya key bisa dipetakan ke provider lain."""
    prefix = (resolved.path_prefix or "").strip("/")
    if prefix and key.startswith(prefix + "/"):
        return key[len(prefix) + 1 :]
    if prefix and key == prefix:
        return ""
    return key


def _target_key(resolved: registry.ResolvedStorage, relative: str) -> str:
    prefix = (resolved.path_prefix or "").strip("/")
    return f"{prefix}/{relative}" if prefix else relative


def _exists(resolved: registry.ResolvedStorage, key: str) -> bool:
    try:
        resolved.client.head_object(Bucket=resolved.bucket, Key=key)
        return True
    except Exception:
        # 403 = tidak punya izin baca: dianggap belum ada supaya copy dicoba dan
        # error aslinya tercatat di hasil job (bukan diam-diam "skipped").
        return False


def _copy_object(
    source: registry.ResolvedStorage,
    target: registry.ResolvedStorage,
    source_key: str,
    target_key: str,
    size: int,
) -> None:
    """Salin satu objek dengan streaming (tanpa menahan seluruh file di RAM)."""
    content_type = "application/octet-stream"
    try:
        head = source.client.head_object(Bucket=source.bucket, Key=source_key)
        content_type = head.get("ContentType") or content_type
    except Exception:
        pass

    if size <= SMALL_OBJECT_BYTES:
        body = source.client.get_object(Bucket=source.bucket, Key=source_key)["Body"].read()
        target.client.put_object(
            Bucket=target.bucket, Key=target_key, Body=body, ContentType=content_type
        )
        return

    handle, tmp_path = tempfile.mkstemp(prefix="clipzi-sync-", suffix=".bin")
    os.close(handle)
    try:
        source.client.download_file(source.bucket, source_key, tmp_path)
        target.client.upload_file(
            tmp_path, target.bucket, target_key, ExtraArgs={"ContentType": content_type}
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _with_retry(action, label: str) -> bool:
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            action()
            return True
        except Exception as exc:
            logger.warning("%s gagal (percobaan %s/%s): %s", label, attempt, RETRY_ATTEMPTS, exc)
            if attempt == RETRY_ATTEMPTS:
                return False
            time.sleep(1.5 * attempt)
    return False


def _run(mode: str, limit: int, max_size_bytes: int) -> None:
    _cancel.clear()
    try:
        primary_item, mirror_items = _resolve_pair()
        primary = registry.resolve(primary_item)
        mirrors = [(item, registry.resolve(item)) for item in mirror_items]
    except Exception as exc:
        _update(state="error", error=str(exc)[:240], finished_at=_now())
        logger.error("Sync storage tidak bisa mulai: %s", exc)
        return

    per_mirror = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "provider": item.get("provider"),
            "bucket": resolved.bucket,
            "listed": 0,
            "copied": 0,
            "skipped": 0,
            "failed": 0,
            "bytes": 0,
            "error": None,
        }
        for item, resolved in mirrors
    ]
    _update(per_mirror=per_mirror, total=0, done=0, copied=0, skipped=0, failed=0, bytes=0)

    try:
        primary_objects = _list_keys(primary)
    except Exception as exc:
        _update(state="error", error=f"gagal membaca primary: {exc}"[:240], finished_at=_now())
        return

    primary_map = {_relative_key(primary, obj["key"]): obj for obj in primary_objects}

    for index, (item, resolved) in enumerate(mirrors):
        if _cancel.is_set():
            break
        mirror_id = str(item.get("id"))
        _update(current=str(item.get("name") or mirror_id))
        try:
            mirror_objects = _list_keys(resolved)
        except Exception as exc:
            with _lock:
                _job["per_mirror"][index]["error"] = str(exc)[:200]
            continue
        mirror_map = {_relative_key(resolved, obj["key"]): obj for obj in mirror_objects}
        with _lock:
            _job["per_mirror"][index]["listed"] = len(mirror_map)

        if mode in ("push", "reconcile"):
            # primary -> mirror
            pending = 0
            for relative, obj in primary_map.items():
                if pending >= limit or _cancel.is_set():
                    break
                if relative in mirror_map:
                    _bump(mirror_id, skipped=1, done=1)
                    continue
                pending += 1
                if obj["size"] > max_size_bytes:
                    _bump(mirror_id, skipped=1, done=1)
                    continue
                ok = _with_retry(
                    lambda rel=relative, size=obj["size"]: _copy_object(
                        primary,
                        resolved,
                        _target_key(primary, rel),
                        _target_key(resolved, rel),
                        size,
                    ),
                    f"copy {mirror_id}:{relative}",
                )
                if ok:
                    _bump(mirror_id, copied=1, bytes=obj["size"], done=1)
                else:
                    _bump(mirror_id, failed=1, done=1)

        if mode in ("reconcile", "heal"):
            # mirror -> primary (pulihkan file yang hilang di primary)
            restored = 0
            for relative, obj in mirror_map.items():
                if _cancel.is_set() or restored >= limit:
                    break
                if relative in primary_map or obj["size"] > max_size_bytes:
                    continue
                ok = _with_retry(
                    lambda rel=relative, src=obj: _copy_object(
                        resolved,
                        primary,
                        src["key"],
                        _target_key(primary, rel),
                        src["size"],
                    ),
                    f"heal {mirror_id}:{relative}",
                )
                if ok:
                    restored += 1
                    _bump(mirror_id, copied=1, bytes=obj["size"], done=1)
                else:
                    _bump(mirror_id, failed=1, done=1)

    state = "cancelled" if _cancel.is_set() else "done"
    _update(state=state, current="", finished_at=_now())


def start_sync(
    mode: str = "push",
    limit: int = DEFAULT_LIMIT,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> Dict[str, Any]:
    """Mulai job sync di background. Tidak pernah menahan request HTTP."""
    global _thread
    if is_running():
        return {"started": False, "message": "Sync masih berjalan", "status": job_status()}
    if not registry.get_config().get("items"):
        return {"started": False, "message": "Storage belum dikonfigurasi", "status": job_status()}

    mode = mode if mode in ("push", "reconcile", "heal") else "push"
    limit = max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))
    max_bytes = max(1, int(max_size_mb or DEFAULT_MAX_SIZE_MB)) * 1024 * 1024

    _update(
        state="running",
        mode=mode,
        started_at=_now(),
        finished_at=None,
        total=0,
        done=0,
        copied=0,
        skipped=0,
        failed=0,
        bytes=0,
        current="",
        error=None,
        per_mirror=[],
    )
    _thread = threading.Thread(
        target=_run, args=(mode, limit, max_bytes), name="clipzi-storage-sync", daemon=True
    )
    _thread.start()
    return {"started": True, "mode": mode, "limit": limit, "max_size_mb": max_size_mb}


def cancel_sync() -> Dict[str, Any]:
    if not is_running():
        return {"cancelled": False, "message": "Tidak ada sync yang berjalan"}
    _cancel.set()
    return {"cancelled": True, "message": "Permintaan batal dikirim"}


def locate(key: str) -> Dict[str, Any]:
    """Cari satu objek di SEMUA provider (primary + mirror)."""
    key = (key or "").strip().lstrip("/")
    if not key:
        return {"key": key, "found": 0, "locations": []}
    config = registry.get_config()
    locations: List[Dict[str, Any]] = []
    for item in config.get("items", []):
        if not item.get("enabled", True):
            continue
        try:
            resolved = registry.resolve(item)
        except Exception as exc:
            locations.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "provider": item.get("provider"),
                    "exists": False,
                    "error": str(exc)[:160],
                }
            )
            continue
        target = _target_key(resolved, key)
        row: Dict[str, Any] = {
            "id": item.get("id"),
            "name": item.get("name"),
            "provider": item.get("provider"),
            "bucket": resolved.bucket,
            "object_key": target,
            "exists": False,
            "size": None,
            "url": None,
        }
        try:
            head = resolved.client.head_object(Bucket=resolved.bucket, Key=target)
            row["exists"] = True
            row["size"] = int(head.get("ContentLength") or 0)
            row["url"] = registry.StorageService()._url(resolved, target)
        except Exception:
            row["exists"] = False
        locations.append(row)
    found = sum(1 for row in locations if row["exists"])
    return {"key": key, "found": found, "locations": locations}




