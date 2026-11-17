#!/usr/bin/env python3
"""
ClipzyAI - agent perintah host (VPS).

Container API tidak punya akses ke `/proc` host maupun docker socket, jadi
aksi admin seperti "Clear Cache VPS" dan "Restart Caddy" dijalankan agent kecil
ini (systemd: `clipzi-host-commands.service`).

Alur:
    GET  /api/internal/host-commands?agent=<hostname>     -> klaim perintah
    POST /api/internal/host-commands/<id>/result          -> kirim hasil

Keamanan:
- hanya aksi di WHITELIST yang bisa dijalankan (nama aksi divalidasi di sini,
  perintah selalu diambil dari tabel lokal — bukan dari API);
- token `X-Clipzi-Token` = CLIPZI_WORKER_TOKEN dari .env;
- output dipotong 4 KB, timeout 120 detik.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(os.environ.get("ENV_FILE", "/opt/clipzi/app/backend/.env"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
INTERVAL = float(os.environ.get("INTERVAL", "3"))
AGENT_NAME = os.environ.get("AGENT_NAME", socket.gethostname())

WHITELIST: dict[str, list[str]] = {
    "clear_cache": ["/bin/sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"],
    "restart_caddy": ["docker", "restart", "clipzi-caddy"],
    "prune_docker": ["docker", "builder", "prune", "-af"],
    # Info OS host + uji kecepatan internet (skrip terpasang oleh installer).
    "os_info": ["/usr/local/sbin/clipzi-osinfo.sh"],
    "speedtest": ["/usr/local/sbin/clipzi-speedtest.sh"],
}


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}", flush=True)


def read_env(name: str) -> str:
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return ""
    return ""


def token() -> str:
    return (os.environ.get("CLIPZI_WORKER_TOKEN") or read_env("CLIPZI_WORKER_TOKEN")).strip()


def request(path: str, method: str = "GET", payload: dict | None = None) -> dict | None:
    secret = token()
    if not secret:
        log("CLIPZI_WORKER_TOKEN kosong - agent tidak bisa menghubungi API")
        return None
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BACKEND_URL}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Clipzi-Token": secret,
            "X-Clipzi-Agent": AGENT_NAME,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        log(f"{method} {path} -> HTTP {exc.code}")
        return None
    except Exception as exc:  # noqa: BLE001 - jaringan putus: coba lagi nanti
        log(f"{method} {path} gagal: {exc}")
        return None


def run_action(action: str) -> tuple[bool, str]:
    command = WHITELIST.get(str(action or "").strip())
    if command is None:
        return False, f"Aksi '{action}' tidak ada di whitelist agent"
    started = time.time()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, f"Timeout 120s saat menjalankan {action}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Gagal menjalankan {action}: {exc}"
    output = "\n".join(
        part.strip() for part in (result.stdout or "", result.stderr or "") if part and part.strip()
    )
    duration = time.time() - started
    log(f"aksi {action}: exit={result.returncode} durasi={duration:.2f}s")
    return result.returncode == 0, (output or f"{action} selesai (exit 0)")[:4000]


def tick() -> None:
    data = request(f"/api/internal/host-commands?agent={AGENT_NAME}")
    if not data:
        return
    for item in data.get("items") or []:
        job_id = str(item.get("id") or "")
        action = str(item.get("action") or "")
        if not job_id:
            continue
        ok, output = run_action(action)
        request(
            f"/api/internal/host-commands/{job_id}/result",
            method="POST",
            payload={"ok": ok, "output": output},
        )


def main() -> int:
    log(f"agent perintah host aktif (backend={BACKEND_URL}, interval={INTERVAL}s)")
    while True:
        try:
            tick()
        except Exception as exc:  # noqa: BLE001 - agent tidak boleh mati
            log(f"tick gagal: {exc}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
