#!/usr/bin/env python3
"""
ClipzyAI - agent metrik host (VPS).

Kenapa ada agent: container API tidak punya akses ke CPU/RAM/disk *host* maupun
docker socket. Agent ini berjalan di host (systemd), membaca /proc + docker CLI,
lalu mengirim snapshot JSON ke API setiap 5 detik:

    POST http://127.0.0.1:8000/api/internal/host-metrics
    header: X-Clipzi-Token: <CLIPZI_WORKER_TOKEN>

API menyimpan snapshot di memori dan dashboard admin (System) menampilkannya
secara realtime. Agent hanya MEMBACA; tidak mengubah apa pun di server.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(os.environ.get("ENV_FILE", "/opt/clipzi/app/backend/.env"))
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
INTERVAL = float(os.environ.get("INTERVAL", "5"))
SAMPLE_SECONDS = 1.0
AGENT_STARTED = time.time()


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {message}", flush=True)


def read_env(name: str) -> str:
    """Ambil satu nilai dari .env tanpa mengeksekusi file (aman dari spasi/kutip)."""
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip()
                return value.strip('"').strip("'")
    except OSError:
        return ""
    return ""


def read_cpu() -> dict:
    """CPU percent dihitung dari delta dua pembacaan /proc/stat."""

    def snapshot() -> tuple[float, float]:
        with open("/proc/stat", encoding="utf-8") as handle:
            first = handle.readline()
        parts = [float(value) for value in first.split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)
        return idle, sum(parts)

    idle_a, total_a = snapshot()
    time.sleep(SAMPLE_SECONDS)
    idle_b, total_b = snapshot()

    total_delta = total_b - total_a
    idle_delta = idle_b - idle_a
    percent = 0.0
    if total_delta > 0:
        percent = max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))

    return {"percent": round(percent, 1), "cores": os.cpu_count() or 1}


def read_memory() -> dict:
    info: dict[str, float] = {}
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            value = rest.strip().split(" ")[0]
            if value.isdigit():
                info[key] = float(value) * 1024.0  # kB -> bytes

    total = info.get("MemTotal", 0.0)
    available = info.get("MemAvailable", info.get("MemFree", 0.0))
    used = max(0.0, total - available)
    swap_total = info.get("SwapTotal", 0.0)
    swap_free = info.get("SwapFree", 0.0)

    def percent(part: float, whole: float) -> float:
        return round(part / whole * 100.0, 1) if whole else 0.0

    return {
        "total": int(total),
        "used": int(used),
        "available": int(available),
        "percent": percent(used, total),
        "swap_total": int(swap_total),
        "swap_used": int(max(0.0, swap_total - swap_free)),
        "swap_percent": percent(max(0.0, swap_total - swap_free), swap_total),
    }


def read_disk() -> dict:
    # statvfs tidak tersedia di Windows (script ini khusus Linux/VPS); abaikan
    # peringatan type checker di editor Windows.
    stats = os.statvfs("/")  # type: ignore[attr-defined]
    total = stats.f_blocks * stats.f_frsize
    free = stats.f_bavail * stats.f_frsize
    used = total - stats.f_bfree * stats.f_frsize
    percent = (used / total * 100.0) if total else 0.0
    return {
        "total": int(total),
        "used": int(used),
        "free": int(free),
        "percent": round(percent, 1),
    }


def read_load() -> dict:
    with open("/proc/loadavg", encoding="utf-8") as handle:
        parts = handle.read().split()
    return {"1": float(parts[0]), "5": float(parts[1]), "15": float(parts[2])}


def read_uptime() -> float:
    with open("/proc/uptime", encoding="utf-8") as handle:
        return float(handle.read().split()[0])


def read_network() -> dict:
    rx = tx = 0
    with open("/proc/net/dev", encoding="utf-8") as handle:
        for line in handle.readlines()[2:]:
            name, _, data = line.partition(":")
            if name.strip() == "lo":
                continue
            columns = data.split()
            if len(columns) < 9:
                continue
            rx += int(columns[0])
            tx += int(columns[8])
    return {"rx_bytes": rx, "tx_bytes": tx}


def run(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _num(text: str) -> float:
    match = re.search(r"[\d.]+", text or "")
    return float(match.group()) if match else 0.0


def parse_started(text: str) -> float | None:
    """Ubah `State.StartedAt` docker (RFC3339, nanodetik) jadi epoch detik."""
    value = (text or "").strip()
    if not value or value.startswith("0001-01-01"):
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    # Python hanya menerima maksimal 6 digit pecahan detik.
    match = re.match(r"^(.*?)(?:\.(\d+))?([+-]\d{2}:\d{2})$", value)
    if match:
        head, frac, tz = match.groups()
        value = f"{head}.{frac[:6]}{tz}" if frac else f"{head}{tz}"
    try:
        from datetime import datetime

        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def read_container_details(names: list[str]) -> dict[str, dict]:
    """Detail container (image, state, uptime, health, restart) via docker inspect."""
    if not names:
        return {}
    fmt = (
        "{{.Name}}|{{.Config.Image}}|{{.State.Status}}|{{.State.StartedAt}}|"
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}|{{.RestartCount}}"
    )
    output = run(["docker", "inspect", "--format", fmt, *names], timeout=15.0)
    details: dict[str, dict] = {}
    now = time.time()
    for line in output.splitlines():
        parts = line.split("|")
        if len(parts) != 6:
            continue
        name = parts[0].lstrip("/")
        started_ts = parse_started(parts[3])
        details[name] = {
            "image": parts[1] or None,
            "state": parts[2] or None,
            "started_at": parts[3] if started_ts else None,
            "uptime_seconds": int(max(0, now - started_ts)) if started_ts else None,
            "health": None if parts[4] in ("", "-") else parts[4],
            "restarts": int(parts[5]) if parts[5].strip().isdigit() else 0,
        }
    return details


def read_containers() -> tuple[list[dict], dict]:
    """Daftar container + CPU/RAM saat ini (docker stats sekali jalan)."""
    status_rows: dict[str, str] = {}
    for line in run(
        ["docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}|{{.Status}}|{{.Image}}"]
    ).splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            status_rows[parts[0]] = f"{parts[1]}|{parts[2]}|{parts[3]}"

    containers: list[dict] = []
    stats_output = run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}",
        ],
        timeout=15.0,
    )
    for line in stats_output.splitlines():
        parts = line.split("|")
        if len(parts) != 4:
            continue
        state = status_rows.get(parts[0], "unknown||")
        state_name, _, rest = state.partition("|")
        status_text, _, image = rest.partition("|")
        containers.append(
            {
                "name": parts[0],
                "state": state_name,
                "status": status_text,
                "image": image or None,
                "cpu_percent": _num(parts[1]),
                "mem_usage": parts[2],
                "mem_percent": _num(parts[3]),
            }
        )

    known = {row["name"] for row in containers}
    for name, state in status_rows.items():
        if name in known:
            continue
        state_name, _, rest = state.partition("|")
        status_text, _, image = rest.partition("|")
        containers.append(
            {
                "name": name,
                "state": state_name,
                "status": status_text,
                "image": image or None,
                "cpu_percent": None,
                "mem_usage": None,
                "mem_percent": None,
            }
        )

    # Detail: image pasti, state, uptime (StartedAt), health, jumlah restart.
    details = read_container_details([row["name"] for row in containers])
    for row in containers:
        found = details.get(row["name"])
        if not found:
            row.setdefault("started_at", None)
            row.setdefault("uptime_seconds", None)
            row.setdefault("health", None)
            row.setdefault("restarts", 0)
            continue
        if found.get("image"):
            row["image"] = found["image"]
        if found.get("state"):
            row["state"] = found["state"]
        row["started_at"] = found.get("started_at")
        row["uptime_seconds"] = found.get("uptime_seconds")
        row["health"] = found.get("health")
        row["restarts"] = found.get("restarts") or 0

    docker_info = run(["docker", "system", "df", "--format", "{{.Type}} {{.Size}} {{.Reclaimable}}"])
    return containers, {
        "total": len(containers),
        "running": len([row for row in containers if row.get("state") == "running"]),
        "disk_usage": docker_info.strip().splitlines()[:4],
    }


def collect() -> dict:
    containers, docker_info = read_containers()
    return {
        "ts": time.time(),
        "hostname": socket.gethostname(),
        "agent": {
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(AGENT_STARTED)),
            "uptime_seconds": int(max(0, time.time() - AGENT_STARTED)),
            "interval_seconds": INTERVAL,
        },
        "cpu": read_cpu(),
        "memory": read_memory(),
        "disk": read_disk(),
        "load": read_load(),
        "uptime_seconds": read_uptime(),
        "network": read_network(),
        "containers": containers,
        "docker": docker_info,
    }


def send(token: str, payload: dict) -> bool:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BACKEND_URL}/api/internal/host-metrics",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Clipzi-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError) as exc:
        log(f"gagal mengirim metrik: {exc}")
        return False


def main() -> int:
    token = read_env("CLIPZI_WORKER_TOKEN") or os.environ.get("CLIPZI_WORKER_TOKEN", "")
    if not token:
        log(f"CLIPZI_WORKER_TOKEN tidak ditemukan di {ENV_FILE}")
        return 1

    log(f"agent metrik mulai: interval {INTERVAL}s, backend {BACKEND_URL}")
    failures = 0
    while True:
        started = time.time()
        try:
            if send(token, collect()):
                failures = 0
            else:
                failures += 1
                if failures in (1, 5, 20):
                    log(f"backend belum menerima metrik ({failures}x)")
        except Exception as exc:  # agent tidak boleh mati karena satu error
            log(f"error saat mengumpulkan metrik: {type(exc).__name__}: {exc}")

        elapsed = time.time() - started
        time.sleep(max(1.0, INTERVAL - elapsed))


if __name__ == "__main__":
    sys.exit(main())
