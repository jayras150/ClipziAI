"""Regresi: entrypoint worker WAJIB mengatur logging INFO ke stdout.

Tanpa ini root logger default WARNING, sehingga semua logger.info (device
Whisper, encoder NVENC, backend YOLO, durasi stage) tidak pernah sampai ke
shipper → admin hanya melihat output yt-dlp dan tidak bisa tahu apakah GPU
dipakai.
"""
from __future__ import annotations

import inspect


def test_entrypoint_mengatur_logging_info_ke_stdout():
    from deployments import run_pipeline

    source = inspect.getsource(run_pipeline._setup_logging)

    assert "basicConfig" in source
    assert "sys.stdout" in source
    assert "force=True" in source
    assert "INFO" in source


def test_entrypoint_mencetak_device_aktual():
    from deployments import run_pipeline

    source = inspect.getsource(run_pipeline._log_runtime)

    assert "get_cuda_device_count" in source
    assert "get_available_providers" in source
    assert "GPU TIDAK TERDETEKSI" in source


def test_onstart_memakai_entrypoint_bukan_inline_c():
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1] / "deployments" / "pipeline_onstart.sh"
    ).read_text(encoding="utf-8")

    assert "/app/deployments/run_pipeline.py" in script


def test_entrypoint_menaruh_app_root_di_syspath():
    """Regresi: /app/deployments/app.py membuat `app` dianggap modul, bukan package.

    Tanpa sys.path.insert(0, /app), worker gagal start dengan
    "No module named 'app.core'; 'app' is not a package" (terbukti di Vast).
    """
    import inspect

    from deployments import run_pipeline

    source = inspect.getsource(run_pipeline)
    assert "sys.path.insert(0, _APP_ROOT)" in source
    assert "os.path.abspath(__file__)" in source
    # `if _APP_ROOT not in sys.path` tidak cukup (folder script tetap menang),
    # jadi folder script WAJIB dibuang dari sys.path.
    assert "_SCRIPT_DIR" in source
    assert "!= _SCRIPT_DIR" in source
