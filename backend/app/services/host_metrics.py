"""
Penyimpan metrik host (VPS) di memori + perhitungan rate.

Kenapa di memori: agent host mengirim snapshot tiap 5 detik lewat
`POST /api/internal/host-metrics`. Data ini bersifat "sekarang" (tidak butuh
histori panjang), jadi tidak perlu tabel/log tambahan. Ring buffer 240 sampel
(~20 menit) dipakai untuk grafik sparkline di dashboard admin.

Container API tidak diberi akses ke docker socket atau /proc host — agent
membaca host dan mengirim JSON, jadi tidak ada eskalasi izin.
"""
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional

MAX_SAMPLES = 240
_STALE_SECONDS = 20

# Service inti yang statusnya selalu ditampilkan di tab System (nama container).
SERVICE_DEFS = (
    ("backend", "Backend API", "clipzi-api"),
    ("frontend", "Frontend web", "clipzi-web"),
    ("admin", "Admin panel", "clipzi-admin"),
    ("caddy", "Reverse proxy (Caddy)", "clipzi-caddy"),
)

_samples: Deque[Dict[str, Any]] = deque(maxlen=MAX_SAMPLES)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rate(current: Optional[float], previous: Optional[float], seconds: float) -> Optional[float]:
    if current is None or previous is None or seconds <= 0:
        return None
    delta = current - previous
    if delta < 0:  # host reboot / counter reset
        return None
    return round(delta / seconds, 1)


def record(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Simpan satu snapshot dari agent, lengkapi dengan rate jaringan."""
    ts = _num(payload.get("ts"), 0) or datetime.now(timezone.utc).timestamp()
    network = payload.get("network") or {}
    rx_total = network.get("rx_bytes")
    tx_total = network.get("tx_bytes")

    rx_rate = None
    tx_rate = None
    if _samples:
        previous = _samples[-1]
        seconds = max(0.0, ts - _num(previous.get("ts"), ts))
        prev_net = previous.get("network") or {}
        rx_rate = _rate(
            None if rx_total is None else _num(rx_total),
            None if prev_net.get("rx_bytes") is None else _num(prev_net.get("rx_bytes")),
            seconds,
        )
        tx_rate = _rate(
            None if tx_total is None else _num(tx_total),
            None if prev_net.get("tx_bytes") is None else _num(prev_net.get("tx_bytes")),
            seconds,
        )

    sample = {
        "ts": ts,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "hostname": payload.get("hostname"),
        "cpu": payload.get("cpu") or {},
        "memory": payload.get("memory") or {},
        "disk": payload.get("disk") or {},
        "load": payload.get("load") or {},
        "uptime_seconds": payload.get("uptime_seconds"),
        "network": {**network, "rx_rate": rx_rate, "tx_rate": tx_rate},
        "containers": payload.get("containers") or [],
        "docker": payload.get("docker") or {},
        "agent": payload.get("agent") or {},
    }
    _samples.append(sample)
    return sample


def services_from(containers: Any) -> list[Dict[str, Any]]:
    """Ringkas status service inti (backend/frontend/admin/caddy) dari container.

    Dipakai tab System supaya admin langsung melihat "backend up 3 hari",
    "caddy healthy", dsb. tanpa membaca tabel container mentah.
    """
    rows = [row for row in (containers or []) if isinstance(row, dict)]
    by_name = {str(row.get("name") or "").strip(): row for row in rows}
    result: list[Dict[str, Any]] = []
    for key, label, container in SERVICE_DEFS:
        row = by_name.get(container)
        if not row:
            result.append(
                {
                    "key": key,
                    "label": label,
                    "container": container,
                    "found": False,
                    "state": "missing",
                    "status": None,
                    "health": None,
                    "image": None,
                    "started_at": None,
                    "uptime_seconds": None,
                    "restarts": 0,
                    "cpu_percent": None,
                    "mem_usage": None,
                    "mem_percent": None,
                    "healthy": False,
                }
            )
            continue
        state = str(row.get("state") or "").strip().lower()
        health = str(row.get("health") or "").strip().lower()
        uptime = row.get("uptime_seconds")
        result.append(
            {
                "key": key,
                "label": label,
                "container": container,
                "found": True,
                "state": state,
                "status": row.get("status"),
                "health": health or None,
                "image": row.get("image"),
                "started_at": row.get("started_at"),
                "uptime_seconds": int(uptime) if isinstance(uptime, (int, float)) else None,
                "restarts": int(row.get("restarts") or 0),
                "cpu_percent": row.get("cpu_percent"),
                "mem_usage": row.get("mem_usage"),
                "mem_percent": row.get("mem_percent"),
                # hijau hanya jika benar-benar berjalan dan (bila ada) healthy
                "healthy": state == "running" and health in ("", "healthy"),
            }
        )
    return result


def latest() -> Optional[Dict[str, Any]]:
    return _samples[-1] if _samples else None


def snapshot() -> Dict[str, Any]:
    """
    Data siap-pakai untuk dashboard admin.

    `stale` = agent berhenti mengirim (mis. timer mati) sehingga UI bisa
    menampilkan peringatan alih-alih angka beku tanpa keterangan.
    """
    current = latest()
    if not current:
        return {"available": False, "stale": True, "history": [], "latest": None, "age_seconds": None}

    age = (datetime.now(timezone.utc) - datetime.fromisoformat(current["received_at"])).total_seconds()
    history = [
        {
            "ts": sample["ts"],
            "time": datetime.fromtimestamp(sample["ts"], tz=timezone.utc).isoformat(),
            "cpu": _num((sample.get("cpu") or {}).get("percent")),
            "memory": _num((sample.get("memory") or {}).get("percent")),
            "disk": _num((sample.get("disk") or {}).get("percent")),
            "rx_rate": (sample.get("network") or {}).get("rx_rate") or 0,
            "tx_rate": (sample.get("network") or {}).get("tx_rate") or 0,
        }
        for sample in _samples
    ]
    return {
        "available": True,
        "stale": age > _STALE_SECONDS,
        "age_seconds": round(age, 1),
        "latest": current,
        "history": history,
    }
