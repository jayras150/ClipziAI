"""
Test penyimpan metrik host (agent VPS -> dashboard System).

Pure unit: tidak butuh DB/agent.
"""
import time


def _payload(ts: float, rx: int, tx: int) -> dict:
    return {
        "ts": ts,
        "hostname": "vps",
        "cpu": {"percent": 12.5, "cores": 2},
        "memory": {"total": 4_000, "used": 2_000, "percent": 50.0},
        "disk": {"total": 100_000, "used": 61_000, "free": 39_000, "percent": 61.0},
        "load": {"1": 0.4, "5": 0.3, "15": 0.2},
        "uptime_seconds": 3600,
        "network": {"rx_bytes": rx, "tx_bytes": tx},
        "containers": [{"name": "clipzi-api", "state": "running", "cpu_percent": 1.0}],
        "docker": {"total": 1, "running": 1},
    }


def test_record_menghitung_rate_jaringan():
    from app.services import host_metrics

    host_metrics._samples.clear()
    now = time.time()
    host_metrics.record(_payload(now, 1_000, 2_000))
    sample = host_metrics.record(_payload(now + 5, 6_000, 4_000))

    # 5000 byte / 5 detik = 1000 B/s ; 2000 / 5 = 400 B/s
    assert sample["network"]["rx_rate"] == 1000.0
    assert sample["network"]["tx_rate"] == 400.0


def test_rate_diabaikan_bila_counter_turun():
    from app.services import host_metrics

    host_metrics._samples.clear()
    now = time.time()
    host_metrics.record(_payload(now, 9_000, 9_000))
    sample = host_metrics.record(_payload(now + 5, 1_000, 1_000))  # host reboot

    assert sample["network"]["rx_rate"] is None
    assert sample["network"]["tx_rate"] is None


def test_snapshot_tersedia_dan_histori_terisi():
    from app.services import host_metrics

    host_metrics._samples.clear()
    now = time.time()
    for index in range(3):
        host_metrics.record(_payload(now + index * 5, index * 100, index * 50))

    data = host_metrics.snapshot()
    assert data["available"] is True
    assert data["stale"] is False
    assert len(data["history"]) == 3
    assert data["latest"]["hostname"] == "vps"
    assert data["history"][-1]["cpu"] == 12.5


def test_snapshot_kosong_tidak_error():
    from app.services import host_metrics

    host_metrics._samples.clear()
    data = host_metrics.snapshot()
    assert data["available"] is False
    assert data["latest"] is None
    assert data["history"] == []
