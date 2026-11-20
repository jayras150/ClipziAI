"""Pembersihan sampah server/container (bukan storage cloud).

`cleanup_manager.py` hanya membersihkan aset cloud (`task_assets`). Modul ini
menangani sampah yang menumpuk di mesin/container API:

  - `temp`  : file sementara milik aplikasi (prefix Clipzi/yt-dlp/reframe) yang
              lebih tua dari `SERVER_CLEANUP_TEMP_TTL_HOURS`.
  - `logs`  : file log aplikasi yang melebihi `SERVER_CLEANUP_LOG_MAX_MB`
              (dipotong, bukan dihapus, supaya log terbaru tetap ada).
  - `cache` : cache cookies yt-dlp yang sudah tidak dipakai.
  - `docker`: image/container/builder sisa build (OPSIONAL, hanya bila
              `SERVER_CLEANUP_DOCKER=true` DAN socket Docker tersedia).

Prinsip keamanan:
  * default `dry_run` — pemanggil harus eksplisit meminta penghapusan;
  * hanya file ber-prefix aplikasi di direktori sementara (tidak menyentuh
    /tmp milik proses lain);
  * tidak pernah menghapus direktori proyek, database, model, atau klip hasil;
  * setiap kegagalan dicatat per-target, tidak menggagalkan target lain.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Hanya file dengan prefix ini yang dianggap sampah aplikasi.
TEMP_PREFIXES = (
    "clipzi-",
    "clipzi_",
    "ytdlp_",
    "reframe_",
    "track_",
    "tmp_clipzi",
)
DEFAULT_TARGETS = ("temp", "logs", "cache")


def _root_dir() -> Path:
    """Direktori kerja aplikasi (isi container), bukan root host."""
    return Path(os.environ.get("CLIPZI_WORK_DIR") or "/app")


def _candidate_temp_dirs() -> List[Path]:
    dirs = [_root_dir() / "tmp", Path("/tmp")]
    seen: List[Path] = []
    for path in dirs:
        try:
            if path.is_dir() and path not in seen:
                seen.append(path)
        except OSError:
            continue
    return seen


def _is_app_temp(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in TEMP_PREFIXES)


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def scan_temp(max_age_hours: int) -> List[Dict[str, Any]]:
    """Daftar file sementara aplikasi yang lebih tua dari batas usia."""
    cutoff = time.time() - max(1, int(max_age_hours)) * 3600
    found: List[Dict[str, Any]] = []
    for directory in _candidate_temp_dirs():
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_file() or not _is_app_temp(entry.name):
                    continue
                stat = entry.stat()
                if stat.st_mtime > cutoff:
                    continue
                found.append(
                    {
                        "path": str(entry),
                        "bytes": stat.st_size,
                        "age_hours": round((time.time() - stat.st_mtime) / 3600, 1),
                    }
                )
            except OSError:
                continue
    return found


def scan_logs(max_mb: int) -> List[Dict[str, Any]]:
    """File log aplikasi yang melebihi batas ukuran."""
    limit = max(1, int(max_mb)) * 1024 * 1024
    root = _root_dir()
    found: List[Dict[str, Any]] = []
    for directory in (root / "logs", root / "tmp"):
        if not directory.is_dir():
            continue
        try:
            entries = list(directory.glob("*.log"))
        except OSError:
            continue
        for entry in entries:
            size = _file_size(entry)
            if size > limit:
                found.append({"path": str(entry), "bytes": size, "excess": size - limit})
    return found


def scan_cache() -> List[Dict[str, Any]]:
    """Cache cookies yt-dlp yang bisa dibuang (file .txt di folder cache)."""
    settings = get_settings()
    directory = Path(settings.YTDLP_COOKIE_CACHE_DIR or "./.cache/ytdlp_cookies")
    if not directory.is_dir():
        return []
    try:
        entries = list(directory.glob("*.txt"))
    except OSError:
        return []
    return [{"path": str(entry), "bytes": _file_size(entry)} for entry in entries]


def _docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return Path("/var/run/docker.sock").exists()


def _run(cmd: Sequence[str], timeout: int = 120) -> Dict[str, Any]:
    """Jalankan perintah tanpa shell (argumen list), kembalikan hasil ringkas."""
    import subprocess

    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 - jangan gagalkan cleanup lain
        return {"command": " ".join(cmd), "ok": False, "error": str(exc)[:300]}
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-3:]
    return {
        "command": " ".join(cmd),
        "ok": proc.returncode == 0,
        "exit": proc.returncode,
        "output": " | ".join(tail)[:400],
    }


def describe() -> Dict[str, Any]:
    """Ringkasan kebijakan + estimasi sampah saat ini (tanpa menghapus)."""
    settings = get_settings()
    temp = scan_temp(settings.SERVER_CLEANUP_TEMP_TTL_HOURS)
    logs = scan_logs(settings.SERVER_CLEANUP_LOG_MAX_MB)
    cache = scan_cache()
    return {
        "enabled": bool(settings.SERVER_CLEANUP_ENABLED),
        "schedule_hour": int(settings.SERVER_CLEANUP_HOUR),
        "temp_ttl_hours": int(settings.SERVER_CLEANUP_TEMP_TTL_HOURS),
        "log_max_mb": int(settings.SERVER_CLEANUP_LOG_MAX_MB),
        "docker_enabled": bool(settings.SERVER_CLEANUP_DOCKER),
        "docker_available": _docker_available(),
        "targets": list(DEFAULT_TARGETS),
        "candidates": {
            "temp": {"files": len(temp), "bytes": sum(item["bytes"] for item in temp)},
            "logs": {"files": len(logs), "bytes": sum(item["excess"] for item in logs)},
            "cache": {"files": len(cache), "bytes": sum(item["bytes"] for item in cache)},
        },
    }


def _clean_temp(max_age_hours: int, dry_run: bool) -> Dict[str, Any]:
    items = scan_temp(max_age_hours)
    removed = 0
    freed = 0
    errors: List[str] = []
    for item in items:
        if dry_run:
            continue
        try:
            Path(item["path"]).unlink(missing_ok=True)
            removed += 1
            freed += int(item["bytes"])
        except OSError as exc:
            errors.append(f"{item['path']}: {exc}")
    return {
        "target": "temp",
        "candidates": len(items),
        "removed": removed,
        "freed_bytes": freed,
        "errors": errors[:5],
    }


def _clean_logs(max_mb: int, dry_run: bool) -> Dict[str, Any]:
    items = scan_logs(max_mb)
    truncated = 0
    freed = 0
    errors: List[str] = []
    limit = max(1, int(max_mb)) * 1024 * 1024
    for item in items:
        if dry_run:
            continue
        path = Path(item["path"])
        try:
            # Potong dari depan: sisakan `limit` byte terakhir (log terbaru).
            data = path.read_bytes()
            keep = data[-limit:]
            path.write_bytes(keep)
            truncated += 1
            freed += max(0, len(data) - len(keep))
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return {
        "target": "logs",
        "candidates": len(items),
        "truncated": truncated,
        "freed_bytes": freed,
        "errors": errors[:5],
    }


def _clean_cache(dry_run: bool) -> Dict[str, Any]:
    items = scan_cache()
    removed = 0
    freed = 0
    errors: List[str] = []
    for item in items:
        if dry_run:
            continue
        try:
            Path(item["path"]).unlink(missing_ok=True)
            removed += 1
            freed += int(item["bytes"])
        except OSError as exc:
            errors.append(f"{item['path']}: {exc}")
    return {
        "target": "cache",
        "candidates": len(items),
        "removed": removed,
        "freed_bytes": freed,
        "errors": errors[:5],
    }


def _clean_docker(dry_run: bool) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.SERVER_CLEANUP_DOCKER:
        return {"target": "docker", "skipped": "disabled"}
    if not _docker_available():
        return {"target": "docker", "skipped": "docker socket tidak tersedia"}
    commands = [
        ["docker", "container", "prune", "-f", "--filter", "until=24h"],
        ["docker", "image", "prune", "-af", "--filter", "until=168h"],
        ["docker", "builder", "prune", "-af"],
    ]
    if dry_run:
        return {
            "target": "docker",
            "dry_run": True,
            "commands": [" ".join(cmd) for cmd in commands],
        }
    return {"target": "docker", "ran": [_run(cmd) for cmd in commands]}


async def cleanup_server(
    dry_run: bool = True, targets: Optional[Sequence[str]] = None
) -> Dict[str, Any]:
    """Jalankan pembersihan sampah server. Default `dry_run=True`."""
    settings = get_settings()
    allowed = DEFAULT_TARGETS + ("docker",)
    wanted = [t for t in (targets or DEFAULT_TARGETS) if t in allowed]
    results: List[Dict[str, Any]] = []

    for target in wanted:
        try:
            if target == "temp":
                results.append(
                    await asyncio.to_thread(
                        _clean_temp, settings.SERVER_CLEANUP_TEMP_TTL_HOURS, dry_run
                    )
                )
            elif target == "logs":
                results.append(
                    await asyncio.to_thread(
                        _clean_logs, settings.SERVER_CLEANUP_LOG_MAX_MB, dry_run
                    )
                )
            elif target == "cache":
                results.append(await asyncio.to_thread(_clean_cache, dry_run))
            elif target == "docker":
                results.append(await asyncio.to_thread(_clean_docker, dry_run))
        except Exception as exc:  # noqa: BLE001 - satu target gagal ≠ semua gagal
            logger.warning("Cleanup target %s gagal: %s", target, exc)
            results.append({"target": target, "error": str(exc)[:300]})

    freed = sum(int(item.get("freed_bytes") or 0) for item in results)
    return {
        "dry_run": dry_run,
        "targets": wanted,
        "results": results,
        "freed_bytes": freed,
        "freed_mb": round(freed / (1024 * 1024), 2),
        "summary": {
            "temp": next(
                (r.get("removed", 0) for r in results if r.get("target") == "temp"), 0
            ),
            "logs": next(
                (r.get("truncated", 0) for r in results if r.get("target") == "logs"), 0
            ),
            "cache": next(
                (r.get("removed", 0) for r in results if r.get("target") == "cache"), 0
            ),
        },
    }


def _seconds_until(hour: int, minute: int = 0) -> float:
    now = datetime.now()
    target = now.replace(
        hour=max(0, min(23, hour)), minute=max(0, min(59, minute)), second=0, microsecond=0
    )
    if target <= now:
        target = target + timedelta(days=1)
    return max(60.0, (target - now).total_seconds())


async def server_cleanup_scheduler() -> None:
    """Loop harian: bersihkan sampah server pada jam yang dikonfigurasi.

    Default mati (`SERVER_CLEANUP_ENABLED=false`) supaya deployment baru tidak
    langsung menghapus apa pun tanpa persetujuan admin.
    """
    settings = get_settings()
    if not settings.SERVER_CLEANUP_ENABLED:
        logger.info("Cleanup server dinonaktifkan (SERVER_CLEANUP_ENABLED=false)")
        return

    hour = int(settings.SERVER_CLEANUP_HOUR)
    logger.info("Cleanup server aktif setiap hari pukul %02d:00", hour)
    while True:
        await asyncio.sleep(_seconds_until(hour))
        try:
            result = await cleanup_server(dry_run=False)
            logger.info(
                "Cleanup server otomatis: %s MB dibebaskan (%s)",
                result.get("freed_mb"),
                result.get("summary"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - loop harus tetap hidup
            logger.warning("Cleanup server error: %s", exc)


