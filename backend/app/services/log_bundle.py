"""
Bundle log worker → unggah ke qurl.sh → kembalikan URL.

Kenapa: log container Vast tidak bisa dibaca dari VPS setelah instance dihapus
(`client.logs()` butuh instance hidup, dan sering timeout). Dengan mengunggah
sekali di akhir task, admin bisa membuka URL-nya kapan saja untuk analisis.

qurl.sh: `PUT https://qurl.sh` (tanpa API key, maks 500 MB, TTL sampai 7 hari).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
import tarfile
import time
from typing import List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

QURL_ENDPOINT = "https://qurl.sh"
WORKER_LOG_PATH = "/tmp/clipzi-worker.log"
LLAMA_LOG_PATH = "/tmp/llama-server.log"

_configured = False


def install_file_logger() -> None:
    """Tulis log proses worker ke /tmp/clipzi-worker.log (sekali saja)."""
    global _configured
    if _configured:
        return
    _configured = True
    try:
        handler = logging.FileHandler(WORKER_LOG_PATH, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        logger.info("File logger worker aktif: %s", WORKER_LOG_PATH)
    except Exception as exc:  # pragma: no cover - filesystem
        logger.warning("Gagal memasang file logger: %s", exc)


def _tail(path: str, limit: int = 200_000) -> Optional[str]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _build_bundle(task_id: str, work_dir: Optional[str]) -> tuple[Optional[str], str]:
    """Buat tar.gz berisi log + info lingkungan. Return (path, error_message)."""
    bundle_path = f"/tmp/clipzi-logs-{str(task_id)[:8]}.tar.gz"
    staging = f"/tmp/clipzi-logstage-{str(task_id)[:8]}"
    try:
        os.makedirs(staging, exist_ok=True)
        for source, name in (
            (WORKER_LOG_PATH, "worker.log"),
            (LLAMA_LOG_PATH, "llama-server.log"),
        ):
            text = _tail(source)
            if text:
                with open(os.path.join(staging, name), "w", encoding="utf-8") as out:
                    out.write(text)

        if work_dir and os.path.isdir(work_dir):
            for name in os.listdir(work_dir):
                if not name.endswith((".srt", ".ass", ".log", ".txt")):
                    continue
                src = os.path.join(work_dir, name)
                try:
                    if os.path.getsize(src) < 2_000_000:
                        with open(src, encoding="utf-8", errors="replace") as handle:
                            content = handle.read()
                        with open(
                            os.path.join(staging, f"work-{name}"), "w", encoding="utf-8"
                        ) as out:
                            out.write(content)
                except Exception:
                    continue

        env_path = os.path.join(staging, "env.txt")
        with open(env_path, "w", encoding="utf-8") as out:
            out.write(
                f"task_id={task_id}\ntime="
                f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
            )
            for key in (
                "GPU_WHISPER_MODEL",
                "TRANSCRIPTION_PROVIDER",
                "AI_MODEL",
                "LOCAL_LLM_MODEL_PATH",
                "LD_LIBRARY_PATH",
            ):
                out.write(f"{key}={os.environ.get(key, '')}\n")

        # Versi paket penting (tanpa shell; pip bisa saja tidak ada).
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "list"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            interesting = [
                line
                for line in (proc.stdout or "").splitlines()
                if any(k in line.lower() for k in ("whisper", "ctranslate", "httpx", "numpy"))
            ]
            with open(env_path, "a", encoding="utf-8") as out:
                out.write("--- pip ---\n" + "\n".join(interesting[:20]) + "\n")
        except Exception as exc:
            with open(env_path, "a", encoding="utf-8") as out:
                out.write(f"--- pip tidak tersedia: {exc} ---\n")

        # Info GPU (kalau nvidia-smi ada).
        try:
            smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            with open(env_path, "a", encoding="utf-8") as out:
                out.write("--- nvidia-smi ---\n" + (smi.stdout or smi.stderr or "")[:500] + "\n")
        except Exception:
            pass

        with tarfile.open(bundle_path, "w:gz") as tar:
            for name in os.listdir(staging):
                tar.add(os.path.join(staging, name), arcname=name)
        return bundle_path, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        try:
            for name in os.listdir(staging):
                os.remove(os.path.join(staging, name))
            os.rmdir(staging)
        except Exception:
            pass


def _parse_url(text: str) -> Optional[str]:
    # qurl.sh membalas sesuatu seperti:
    #   ✔ Success - uploaded file.tgz (12 KB)\nhttps://qurl.sh/abcd/file.tgz
    for token in re.findall(r"https://qurl\.sh/\S+", text or ""):
        if "/qr/" not in token:
            return token.rstrip(".,)")
    return None


async def upload_log_bundle(
    task_id: str, work_dir: Optional[str] = None
) -> tuple[Optional[str], str]:
    """Unggah bundle log ke qurl.sh.

    Return `(url, error)`: url terisi kalau sukses, error berisi alasan bila gagal
    (dipakai worker untuk melaporkan `logs_failed` ke admin).
    """
    settings = get_settings()
    if not getattr(settings, "WORKER_LOG_UPLOAD", True):
        return None, "WORKER_LOG_UPLOAD=false"

    bundle_path, build_error = await asyncio.to_thread(
        _build_bundle, str(task_id), work_dir
    )
    if not bundle_path:
        return None, f"bundle gagal dibuat: {build_error}"

    try:
        with open(bundle_path, "rb") as handle:
            content = handle.read()
        # qurl.sh butuh nama file di path (seperti upload dari pipe), dan
        # `X-Format: url` membuat balasannya hanya URL (mudah diparse).
        endpoint = f"{QURL_ENDPOINT}/{os.path.basename(bundle_path)}"
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.put(
                endpoint,
                content=content,
                headers={
                    "Content-Type": "application/gzip",
                    "X-TTL": "7d",
                    "X-Downloads": "100",
                    "X-Format": "url",
                },
            )
        text = (response.text or "").strip()
        url = text if text.startswith("http") else _parse_url(text)
        if url:
            logger.info("Log worker terunggah: %s", url)
            return url, ""
        logger.warning("qurl.sh membalas tanpa URL: %s", text[:200])
        return None, f"qurl tanpa URL (HTTP {response.status_code}): {text[:200]}"
    except Exception as exc:
        logger.warning("Upload log ke qurl.sh gagal: %s", str(exc)[:200])
        return None, f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            os.remove(bundle_path)
        except Exception:
            pass
