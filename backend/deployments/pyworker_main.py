"""
Entrypoint worker Vast.ai **serverless** untuk Clipzi AI.

Kenapa perlu file ini: engine Vast hanya mau mengirim request ke worker yang
melaporkan `ready`. Laporan itu dikirim oleh **PyWorker** (framework di dalam
paket `vastai`), bukan oleh service FastAPI kita. Tanpa PyWorker, worker berhenti
di status `model_loading` dan log endpoint menampilkan:

    error queue_work: endpoint ... failed to find rdy worker

Pembagian port di dalam container:

| Proses | Port | Peran |
|--------|------|-------|
| PyWorker (`Worker(...).run()`) | `WORKER_PORT` (default 8000, **inilah yang di-`-p 8000:8000`**) | proxy + pelapor ready + penghitung beban autoscaling |
| Service FastAPI (`deployments/worker_api.py`) | `MODEL_SERVER_PORT` (default 18000, localhost saja) | menjalankan pipeline video |

Request dari API utama tetap ke route `/process`; PyWorker meneruskannya ke
`http://127.0.0.1:${MODEL_SERVER_PORT}/process`.

Jalankan lokal (tanpa Vast) untuk menguji:

    CLIPZI_WORKER_MODE=api python -m deployments.worker_api  # tanpa PyWorker
    python -m deployments.pyworker_main                     # dengan PyWorker
"""
from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys

MODEL_PORT = int(os.environ.get("MODEL_SERVER_PORT", "18000"))
MODEL_LOG = os.environ.get("MODEL_LOG_FILE", "/var/log/model/server.log")
APP_DIR = os.environ.get("CLIPZI_APP_DIR", os.getcwd())
WORKER_PORT = int(os.environ.get("WORKER_PORT", "8000"))
MAX_QUEUE_TIME = float(os.environ.get("WORKER_MAX_QUEUE_TIME", "300"))
# Baris log uvicorn yang menandakan model server siap menerima request.
STARTUP_MARKER = "Application startup complete."


def _spawn_model_server() -> tuple[subprocess.Popen, "pathlib.Path"]:
    """Jalankan service FastAPI pipeline di localhost (bukan port publik)."""
    log_path = pathlib.Path(MODEL_LOG)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # direktori read-only: log ke stdout container
        log_path = pathlib.Path("/tmp/clipzi-model-server.log")
    log_handle = log_path.open("a", buffering=1, encoding="utf-8")
    cmd = [
        sys.executable, "-m", "uvicorn", "deployments.worker_api:app",
        "--host", "127.0.0.1",
        "--port", str(MODEL_PORT),
        "--log-level", "info",
    ]
    print(f"[pyworker] model server: {' '.join(cmd)} (log: {log_path})", flush=True)
    proc = subprocess.Popen(cmd, cwd=APP_DIR, stdout=log_handle, stderr=subprocess.STDOUT)
    log_handle.close()  # anak proses sudah memegang deskriptornya sendiri
    return proc, log_path


def build_config():
    """Susun WorkerConfig PyWorker untuk satu route: `/process`."""
    from vastai import HandlerConfig, LogActionConfig, WorkerConfig

    return WorkerConfig(
        model_server_url="http://127.0.0.1",
        model_server_port=MODEL_PORT,
        model_log_file=MODEL_LOG,
        handlers=[
            HandlerConfig(
                route="/process",
                healthcheck="/health",
                # Pipeline video memakai GPU secara eksklusif -> satu job/worker.
                allow_parallel_requests=False,
                max_queue_time=MAX_QUEUE_TIME,
                # Beban seragam per video; cukup untuk autoscaling berbasis load.
                workload_calculator=lambda payload: 100.0,
            )
        ],
        log_action_config=LogActionConfig(
            on_load=[STARTUP_MARKER],
            on_error=["Traceback (most recent call last):", "RuntimeError:"],
        ),
    )


def main() -> int:
    from vastai import Worker

    if not os.environ.get("WORKER_PORT"):
        os.environ["WORKER_PORT"] = str(WORKER_PORT)  # dibaca PyWorker saat listen
    print(
        f"[pyworker] listen WORKER_PORT={os.environ['WORKER_PORT']}, "
        f"model server port={MODEL_PORT}",
        flush=True,
    )

    model_proc, _log_path = _spawn_model_server()

    def _stop(signum, _frame) -> None:  # noqa: ANN001 - handler signal
        print(f"[pyworker] sinyal {signum}: menghentikan model server", flush=True)
        if model_proc.poll() is None:
            model_proc.terminate()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        Worker(build_config()).run()
        return 0
    finally:
        if model_proc.poll() is None:
            model_proc.terminate()
        try:
            model_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - proses keras
            model_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
