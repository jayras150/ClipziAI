#!/usr/bin/env python3
"""
Jalankan SATU task di instance Vast.ai sekali pakai:

    search offer -> create instance -> tunggu task selesai -> DESTROY instance

Ini mode "ephemeral per job": GPU hanya hidup selama task berjalan, lalu instance
dihapus sehingga tagihan berhenti. Cocok untuk skenario "user klik start clip".

    python scripts/vastai-run-once.py --task-id <uuid>
    python scripts/vastai-run-once.py --task-id <uuid> --dry-run
    python scripts/vastai-run-once.py --task-id <uuid> --keep     # jangan destroy

Perbandingan dengan mode endpoint (default di Clipzi):

| Mode                | Cara kerja                          | Cold start | Biaya idle |
|---------------------|-------------------------------------|------------|-----------|
| Endpoint + scale-0  | engine buat/hapus worker otomatis   | ~1–3 menit | 0 (GPU)   |
| One-shot (script ini)| instance dibuat & dihapus per task | ~2–5 menit | 0          |

Rahasia TIDAK dikirim lewat argumen CLI (muncul di process list). Script memakai
Environment Variables tingkat akun Vast. Siapkan sekali:

    vastai create env-var DATABASE_URL "postgresql+asyncpg://..."
    vastai create env-var REDIS_URL "rediss://default:...@....upstash.io:6379"
    vastai create env-var R2_ACCESS_KEY_ID "..."
    vastai create env-var R2_SECRET_ACCESS_KEY "..."
    vastai create env-var R2_ENDPOINT_URL "..."
    vastai create env-var R2_BUCKET_NAME "..."
    vastai create env-var R2_PUBLIC_DOMAIN "..."
    vastai create env-var SECRET_KEY "..."
    vastai create env-var ENCRYPTION_KEY "..."
    vastai create env-var AI_API_KEY "..."
    vastai create env-var TRANSCRIPTION_PROVIDER "groq"
    vastai create env-var TRANSCRIPTION_API_KEY "..."
    vastai create env-var TRANSCRIPTION_BASE_URL "https://api.groq.com/openai/v1"
    vastai create env-var TRANSCRIPTION_MODEL "whisper-large-v3-turbo"

Atau dorong otomatis dari backend/.env:  tambahkan --push-env
"""
import argparse
import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "backend"
ENV_FILE = BACKEND_DIR / ".env"

# Variabel yang dibutuhkan pipeline di dalam worker
ENV_WHITELIST = (
    "DATABASE_URL",
    "REDIS_URL",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT_URL",
    "R2_BUCKET_NAME",
    "R2_PUBLIC_DOMAIN",
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "AI_PROVIDER",
    "AI_API_KEY",
    "AI_BASE_URL",
    "AI_MODEL",
    "TRANSCRIPTION_PROVIDER",
    "TRANSCRIPTION_API_KEY",
    "TRANSCRIPTION_BASE_URL",
    "TRANSCRIPTION_MODEL",
    "YTDLP_COOKIES_BASE64",
    "YTDLP_PROXY",
    "YTDLP_EXTRACTOR_ARGS",
)

REQUIRED_ENV = ("DATABASE_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT_URL")


def load_env_file() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cfg(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def fail(message: str) -> "None":
    print(f"\n[ERROR] {message}\n", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: List[str], capture: bool = True) -> str:
    print("> " + shlex.join(cmd), flush=True)
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        fail(f"perintah gagal (exit {result.returncode})\n{detail}")
    return (result.stdout or "").strip() if capture else ""


def show(cmd: List[str]) -> None:
    print("> " + shlex.join(cmd), flush=True)

def push_env_vars(dry_run: bool) -> None:
    """Dorong variabel whitelist dari backend/.env ke Environment Variables akun Vast."""
    print("\n=== Push env vars ke akun Vast.ai ===")
    pushed = 0
    for name in ENV_WHITELIST:
        value = cfg(name)
        if not value:
            continue
        if dry_run:
            show(["vastai", "create", "env-var", name, "********"])
        else:
            run(["vastai", "create", "env-var", name, value])
        pushed += 1
    print(f"{pushed} variabel diproses.")


def check_account_env(dry_run: bool) -> None:
    """Peringatkan bila variabel wajib belum ada di akun Vast."""
    if dry_run:
        return
    raw = run(["vastai", "show", "env-vars", "--raw"])
    try:
        items = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return
    names = {
        str(item.get("name") or item.get("key") or "")
        for item in items
        if isinstance(item, dict)
    }
    missing = [name for name in REQUIRED_ENV if name not in names]
    if missing:
        print("\n[!] Variabel berikut belum ada di akun Vast:")
        for name in missing:
            print(f"      - {name}")
        print("    Jalankan sekali dengan --push-env, atau:")
        print("      vastai create env-var NAME VALUE")


def search_offer(max_price: float, gpu_filter: str) -> Dict[str, Any]:
    query = f"{gpu_filter} rentable=true num_gpus=1".strip()
    offers = json.loads(run(["vastai", "search", "offers", "--raw", query]) or "[]")

    usable = [
        offer
        for offer in offers
        if offer.get("rentable")
        and float(offer.get("dph_total") or 0) > 0
        and (max_price <= 0 or float(offer.get("dph_total") or 0) <= max_price)
    ]
    if not usable:
        fail(f"tidak ada offer yang cocok (filter: {query}, max_price: {max_price or 'bebas'})")

    usable.sort(key=lambda offer: float(offer.get("dph_total") or 0))
    return usable[0]


def write_onstart_script(task_id: str) -> Path:
    """Tulis script onstart ke file sementara (dipakai `--onstart`).

    Memakai file menghindari quoting berlapis pada `--onstart-cmd`.
    """
    script_path = Path(tempfile.gettempdir()) / f"clipzi-onstart-{task_id[:8]}.sh"
    script_path.write_text(
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        "cd /app\n"
        "python -c 'import asyncio; from uuid import UUID; "
        "from app.services.pipeline import run_video_pipeline; "
        'r = asyncio.run(run_video_pipeline(UUID("' + str(task_id) + '"))); '
        'print("PIPELINE_RESULT", r); '
        'raise SystemExit(0 if r.get("ok") else 1)\'\n',
        encoding="utf-8",
        newline="\n",
    )
    return script_path


def create_instance(offer_id: Any, task_id: str, args) -> str:
    image = cfg("VAST_WORKER_IMAGE")
    template_hash = cfg("VAST_TEMPLATE_HASH")
    if not image and not template_hash:
        fail("isi VAST_WORKER_IMAGE (atau VAST_TEMPLATE_HASH) di backend/.env lebih dulu")

    cmd = [
        "vastai", "create", "instance", str(offer_id),
        "--disk", str(cfg("VAST_WORKER_DISK", "40")),
        "--label", f"clipzi-{task_id[:8]}",
        "--env", "-e CLIPZI_ROLE=worker",
        "--cancel-unavail",
        "--raw",
    ]

    if args.dry_run:
        cmd += ["--onstart", "<script>"]
        if template_hash:
            cmd += ["--template_hash", template_hash]
        else:
            cmd += ["--image", image]
        show(cmd)
        return "<INSTANCE_ID>"

    onstart_file = write_onstart_script(task_id)
    cmd += ["--onstart", str(onstart_file)]
    if template_hash:
        cmd += ["--template_hash", template_hash]
    else:
        cmd += ["--image", image]

    output = run(cmd)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        fail(f"tidak bisa membaca output create instance:\n{output}")
    instance_id = payload.get("new_contract") or payload.get("instance_id") or payload.get("id")
    if not instance_id:
        fail(f"instance id tidak ditemukan pada output:\n{output}")
    return str(instance_id)


async def _wait_task(task_id: str, timeout: int, interval: int = 15) -> str:
    """Polling status task di PostgreSQL sampai selesai/error/timeout."""
    sys.path.insert(0, str(BACKEND_DIR))
    from uuid import UUID

    from app.db.session import AsyncSessionLocal
    from app.models.task import Task

    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, UUID(task_id))
            if task is None:
                return "not_found"
            status = task.status.value if hasattr(task.status, "value") else str(task.status)
            progress = task.progress
        if status != last_status:
            print(f"   status={status} progress={progress}%", flush=True)
            last_status = status
        if status in ("completed", "error", "cancelled"):
            return status
        await asyncio.sleep(interval)
    return "timeout"


def destroy_instance(instance_id: str, dry_run: bool) -> None:
    if instance_id.startswith("<"):
        print("[dry-run] destroy dilewati")
        return
    cmd = ["vastai", "destroy", "instance", instance_id, "-y", "--raw"]
    if dry_run:
        show(cmd)
        return
    run(cmd)
    print(f"Instance {instance_id} dihapus — tagihan GPU berhenti.")


def main() -> int:
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Sekali pakai: create instance Vast -> jalankan 1 task -> destroy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--task-id", required=True, help="UUID task yang akan diproses")
    parser.add_argument("--gpu", default=None, help="filter GPU (default: VAST_GPU_FILTER)")
    parser.add_argument("--max-price", type=float, default=0.0, help="harga maks $/jam (0 = bebas)")
    parser.add_argument("--timeout", type=int, default=3600, help="batas detik menunggu task")
    parser.add_argument("--keep", action="store_true", help="JANGAN destroy instance di akhir")
    parser.add_argument("--push-env", action="store_true", help="dorong backend/.env ke env-vars akun Vast")
    parser.add_argument("--dry-run", action="store_true", help="tampilkan perintah tanpa eksekusi")
    args = parser.parse_args()

    if shutil.which("vastai") is None and not args.dry_run:
        fail("CLI `vastai` tidak ditemukan.\nInstall: pip install vastai\nLalu: vastai set api-key <KEY>")

    if args.push_env:
        push_env_vars(args.dry_run)

    check_account_env(args.dry_run)

    gpu_filter = args.gpu or cfg("VAST_GPU_FILTER", "gpu_ram>=16 disk_space>=40")
    print(f"\n=== Cari offer GPU: {gpu_filter} ===")
    if args.dry_run:
        offer: Dict[str, Any] = {"id": "<OFFER_ID>", "gpu_name": "<gpu>", "dph_total": 0.0}
    else:
        offer = search_offer(args.max_price, gpu_filter)
    price = float(offer.get("dph_total") or 0)
    print(f"   offer={offer.get('id')} gpu={offer.get('gpu_name')} ${price:.3f}/jam")

    instance_id = create_instance(offer.get("id"), args.task_id, args)
    print(f"   instance id: {instance_id}")

    status = "unknown"
    try:
        if args.dry_run:
            print("\n[dry-run] instance tidak dibuat; polling dilewati.")
        else:
            print("\n=== Menunggu task selesai (polling DB) ===")
            status = asyncio.run(_wait_task(args.task_id, args.timeout))
            print(f"   hasil task: {status}")
    finally:
        print("\n=== Cleanup ===")
        if args.keep:
            print(f"[--keep] instance DIBIARKAN hidup. Hapus manual:")
            print(f"    vastai destroy instance {instance_id} -y")
        else:
            destroy_instance(instance_id, args.dry_run)

    return 0 if status in ("completed", "unknown") else 1


if __name__ == "__main__":
    raise SystemExit(main())

