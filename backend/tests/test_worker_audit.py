"""Tes audit worker + antrean perintah host (tab System)."""
from app.services import host_commands, worker_logs


def test_outcome_from_memetakan_state():
    assert worker_logs.outcome_from("failed") == "failed"
    assert worker_logs.outcome_from("error") == "failed"
    assert worker_logs.outcome_from("exited") == "cancelled"
    assert worker_logs.outcome_from("running") == "running"
    assert worker_logs.outcome_from("destroyed", "task selesai") == "success"
    assert worker_logs.outcome_from("destroyed", "admin manual") == "failed"
    assert worker_logs.outcome_from("destroyed", "dibatalkan: user") == "cancelled"
    assert worker_logs.outcome_from("destroyed", None) == "success"


def test_host_command_enqueue_dan_selesai():
    job = host_commands.enqueue("clear_cache", requested_by="test")
    assert job["status"] == "pending"
    pending = host_commands.pending_for("vps-1")
    assert any(item["id"] == job["id"] for item in pending)
    assert host_commands.pending_for("vps-1") == []
    done = host_commands.finish(job["id"], True, "cache dibersihkan")
    assert done is not None
    assert done["status"] == "done"
    assert done["ok"] is True
    assert "cache" in done["output"]


def test_host_command_menolak_aksi_asing():
    try:
        host_commands.enqueue("rm -rf /")
    except ValueError as exc:
        assert "tidak dikenal" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("aksi asing harus ditolak")


def test_host_command_output_dipotong():
    # Backup/restore menghasilkan log panjang, jadi batas output 12000 karakter.
    job = host_commands.enqueue("restart_caddy")
    done = host_commands.finish(job["id"], False, "x" * 30_000)
    assert done is not None
    assert len(done["output"]) <= host_commands.MAX_OUTPUT == 12_000
    assert done["ok"] is False


def test_daftar_aksi_tersedia():
    ids = {item["id"] for item in host_commands.actions()}
    assert {"clear_cache", "restart_caddy", "prune_docker", "backup_now", "restore_backup"} <= ids
