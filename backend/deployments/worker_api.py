"""
Worker HTTP API — dijalankan di GPU worker Vast.ai (atau lokal untuk uji).

Jalankan:
    uvicorn deployments.worker_api:app --host 0.0.0.0 --port 8000

Endpoint:
    GET  /health        -> liveness (tanpa akses DB/R2) untuk healthcheck Docker
    GET  /ready         -> readiness yang dipantau PyWorker sebelum menerima request
    POST /process       -> {"task_id": "..."} jalankan pipeline di background
    POST /process-sync  -> sama, tetapi menunggu selesai (debug/uji lokal)

API utama (VPS) mengirim job ke sini lewat app/services/vast_worker.py.
"""
import logging
from uuid import UUID

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.pipeline import run_video_pipeline

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Clipzi Video Worker",
    version=settings.APP_VERSION,
    description="GPU worker untuk pemrosesan video Clipzi AI",
)


class ProcessRequest(BaseModel):
    task_id: UUID


@app.get("/health")
async def health() -> dict:
    """Liveness ringan — sengaja tidak menyentuh DB agar healthcheck cepat."""
    return {"status": "ok", "service": "clipzi-worker", "version": settings.APP_VERSION}


@app.get("/ready")
async def ready() -> dict:
    """Readiness untuk PyWorker Vast.ai.

    Worker dianggap siap begitu proses HTTP hidup. Dependency eksternal
    (Postgres/Redis/R2) tidak diperiksa di sini supaya worker tidak terus
    berstatus "loading" hanya karena gangguan jaringan sesaat.
    """
    return {"ready": True, "service": "clipzi-worker"}


@app.post("/process")
async def process(payload: ProcessRequest, background: BackgroundTasks) -> dict:
    """Terima job dan jalankan pipeline di background."""
    logger.info("Worker menerima task %s", payload.task_id)
    background.add_task(run_video_pipeline, payload.task_id)
    return {"accepted": True, "task_id": str(payload.task_id)}


@app.post("/ping")
async def ping() -> dict:
    """Route super ringan untuk benchmark PyWorker (tanpa DB/GPU).

    PyWorker mewajibkan tepat satu handler punya `BenchmarkConfig`. Benchmark
    tidak boleh menjalankan pipeline sungguhan (mahal & butuh task nyata), jadi
    kapasitas worker diukur lewat route ini.
    """
    return {"ok": True, "service": "clipzi-worker"}


@app.post("/process-sync")
async def process_sync(payload: ProcessRequest) -> dict:
    """Jalankan pipeline dan tunggu hasilnya (untuk uji lokal/debug)."""
    result = await run_video_pipeline(payload.task_id)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error") or "pipeline gagal")
    return result


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "deployments.worker_api:app",
        host="0.0.0.0",
        port=settings.WORKER_PORT,
    )
