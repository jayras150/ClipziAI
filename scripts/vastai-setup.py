#!/usr/bin/env python3
"""
Kelola endpoint + workergroup Vast.ai Serverless untuk Clipzi AI.

Pemakaian:
    python scripts/vastai-setup.py template    # buat template worker -> dapat hash
    python scripts/vastai-setup.py create      # buat endpoint + workergroup
    python scripts/vastai-setup.py update      # terapkan perubahan scaling
    python scripts/vastai-setup.py status      # lihat endpoint & worker
    python scripts/vastai-setup.py logs        # 100 baris log endpoint
    python scripts/vastai-setup.py benchmark   # cari GPU terbaik (perf/$)
    python scripts/vastai-setup.py teardown    # hapus workergroup + endpoint

Tambahkan --dry-run di depan subcommand untuk melihat perintah tanpa menjalankan.

Konfigurasi dibaca dari backend/.env (otomatis) atau environment:
    VAST_API_KEY, VAST_ENDPOINT_NAME, VAST_TEMPLATE_HASH, VAST_WORKER_IMAGE,
    VAST_GPU_FILTER, VAST_MIN_WORKERS, VAST_MAX_WORKERS, VAST_TARGET_UTIL,
    VAST_INACTIVITY_TIMEOUT, VAST_ENDPOINT_ID, VAST_WORKERGROUP_ID

Membutuhkan CLI resmi: pip install vastai && vastai set api-key <KEY>
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "backend" / ".env"


def load_env_file() -> None:
    """Muat KEY=VALUE dari backend/.env tanpa menimpa env yang sudah ada."""
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


def run(cmd: list) -> str:
    """Jalankan perintah; kembalikan stdout (atau string kosong)."""
    print("> " + shlex.join(cmd), flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        fail(f"perintah gagal (exit {result.returncode})\n{detail}")
    return (result.stdout or "").strip()


def show(cmd: list) -> None:
    """Tampilkan perintah (amannya bisa di-copy-paste)."""
    print("> " + shlex.join(cmd), flush=True)


def build_launch_args() -> str:
    """Susun launch_args: worker role + image + disk."""
    parts = []
    image = cfg("VAST_WORKER_IMAGE")
    if image:
        parts.append(f"--image {image}")
    parts.append("--env '-e CLIPZI_ROLE=worker'")
    parts.append("--env '-e WORKER_PORT=8000'")
    parts.append("--disk 40")
    return " ".join(parts)


def endpoint_create_cmd() -> list:
    return [
        "vastai", "create", "endpoint",
        "--endpoint_name", cfg("VAST_ENDPOINT_NAME", "clipzi-processing"),
        "--target_util", cfg("VAST_TARGET_UTIL", "0.9"),
        "--cold_mult", cfg("VAST_COLD_MULT", "2.0"),
        "--cold_workers", cfg("VAST_COLD_WORKERS", "1"),
        "--max_workers", cfg("VAST_MAX_WORKERS", "4"),
        "--max_queue_time", cfg("VAST_MAX_QUEUE_TIME", "120"),
        "--target_queue_time", cfg("VAST_TARGET_QUEUE_TIME", "20"),
        "--inactivity_timeout", cfg("VAST_INACTIVITY_TIMEOUT", "300"),
    ]


def workergroup_create_cmd() -> list:
    cmd = [
        "vastai", "create", "workergroup",
        "--endpoint_name", cfg("VAST_ENDPOINT_NAME", "clipzi-processing"),
        "--launch_args", build_launch_args(),
    ]
    template_hash = cfg("VAST_TEMPLATE_HASH")
    if template_hash:
        cmd += ["--template_hash", template_hash]
    else:
        cmd += ["--search_params", cfg("VAST_GPU_FILTER", "gpu_ram>=16 disk_space>=40")]
    return cmd


def template_create_cmd() -> list:
    """Perintah membuat template worker (pembungkus `docker run`).

    Template menyimpan: image, port yang dibuka, env yang di-set, dan disk.
    Hash hasil pembuatan dipakai di VAST_TEMPLATE_HASH.
    """
    cmd = [
        "vastai", "create", "template",
        "--name", cfg("VAST_TEMPLATE_NAME", "clipzi-worker"),
        "--image", cfg("VAST_WORKER_IMAGE") or "<user>/clipzi-backend:1.0.0",
        "--env", "-p 8000:8000 -e CLIPZI_ROLE=worker",
        "--disk_space", cfg("VAST_WORKER_DISK", "40"),
        "--desc", "Clipzi AI GPU worker (FastAPI + ffmpeg + yt-dlp)",
    ]
    onstart = cfg("VAST_WORKER_ONSTART")
    if onstart:
        cmd += ["--onstart-cmd", onstart]
    if cfg("VAST_TEMPLATE_PUBLIC").lower() in ("1", "true", "yes"):
        cmd.append("--public")
    return cmd


def find_ids() -> tuple:
    """Ambil (endpoint_id, workergroup_id) dari API Vast (butuh --raw)."""
    endpoint_id = cfg("VAST_ENDPOINT_ID")
    workergroup_id = cfg("VAST_WORKERGROUP_ID")
    name = cfg("VAST_ENDPOINT_NAME", "clipzi-processing")

    if not endpoint_id:
        raw = run(["vastai", "show", "endpoints", "--raw"])
        for item in _as_list(raw):
            if str(item.get("endpoint_name") or item.get("name")) == name:
                endpoint_id = str(item.get("id"))
                break

    if not workergroup_id:
        raw = run(["vastai", "show", "workergroups", "--raw"])
        for item in _as_list(raw):
            if str(item.get("endpoint_name") or item.get("name")) == name:
                workergroup_id = str(item.get("id"))
                break

    return endpoint_id, workergroup_id


def _as_list(raw: str) -> list:
    """Parse keluaran --raw (JSON list) dengan toleransi."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        for key in ("endpoints", "workergroups", "results", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return []
    return data if isinstance(data, list) else []


def find_endpoint_by_name() -> Optional[dict]:
    """Cari endpoint yang sudah ada dengan nama dari konfigurasi (read-only)."""
    name = cfg("VAST_ENDPOINT_NAME", "clipzi-processing")
    raw = run(["vastai", "show", "endpoints", "--raw"])
    for item in _as_list(raw):
        if str(item.get("endpoint_name") or item.get("name")) == name:
            return item
    return None


def cmd_activate(args) -> None:
    """Aktifkan atau hentikan endpoint (endpoint_state active|stopped)."""
    endpoint_id = args.endpoint_id or cfg("VAST_ENDPOINT_ID")
    if not endpoint_id:
        existing = find_endpoint_by_name()
        endpoint_id = str(existing.get("id")) if existing else ""
    if not endpoint_id:
        fail("endpoint tidak ditemukan. Buat dulu: python scripts/vastai-setup.py create")

    state = "stopped" if args.stop else "active"
    cmd = ["vastai", "update", "endpoint", str(endpoint_id), "--endpoint_state", state]
    print(f"\n=== Set endpoint {endpoint_id} -> {state} ===")
    if args.dry_run:
        show(cmd)
        return
    run(cmd)
    print(f"Endpoint {endpoint_id} sekarang: {state}")


def cmd_create(args) -> None:
    name = cfg("VAST_ENDPOINT_NAME", "clipzi-processing")
    print(f"\n=== Endpoint '{name}' ===")

    if args.dry_run:
        show(endpoint_create_cmd())
        show(workergroup_create_cmd())
        return

    # Idempotent: jangan buat endpoint baru kalau namanya sudah ada.
    existing = find_endpoint_by_name()
    if existing:
        print(
            f"Endpoint sudah ada: id={existing.get('id')} "
            f"state={existing.get('endpoint_state')} "
            f"max_workers={existing.get('max_workers')}"
        )
        print("Melewati pembuatan endpoint. (ubah parameter pakai: ... update)")
    else:
        run(endpoint_create_cmd())

    print("\n=== Workergroup (worker GPU) ===")
    run(workergroup_create_cmd())
    print("\nSelesai. Jalankan `python scripts/vastai-setup.py status` untuk melihat")
    print("URL endpoint, lalu isi VAST_ENDPOINT_URL (atau VAST_API_KEY + VAST_ENDPOINT_NAME)")
    print("Kalau endpoint berstatus 'stopped', aktifkan: python scripts/vastai-setup.py activate")


def cmd_template(args) -> None:
    """Buat template worker lalu cetak hash-nya (untuk VAST_TEMPLATE_HASH)."""
    image = cfg("VAST_WORKER_IMAGE")
    if not image and not args.dry_run:
        fail(
            "VAST_WORKER_IMAGE kosong.\n"
            "Isi di backend/.env dengan image backend Anda, contoh:\n"
            "  VAST_WORKER_IMAGE=budi/clipzi-backend:1.0.0"
        )

    cmd = template_create_cmd()
    print(f"\n=== Membuat template '{cfg('VAST_TEMPLATE_NAME', 'clipzi-worker')}' ===")
    if args.dry_run:
        show(cmd)
        return

    run(cmd)

    name = cfg("VAST_TEMPLATE_NAME", "clipzi-worker")
    print("\n=== Mencari hash template ===")
    for item in _as_list(run(["vastai", "show", "templates", "--raw"])):
        if str(item.get("name")) != name:
            continue
        template_hash = item.get("hash") or item.get("template_hash") or item.get("id")
        print(f"  nama : {name}")
        print(f"  hash : {template_hash}")
        print(f"  id   : {item.get('id')}")
        print("\nTambahkan ke backend/.env:")
        print(f"  VAST_TEMPLATE_HASH={template_hash}")
        return

    print("Template dibuat, tetapi hash tidak ditemukan otomatis.")
    print("Buka cloud.vast.ai/templates dan salin hash dari kartu template,")
    print("atau jalankan: vastai show templates")


def cmd_update(args) -> None:
    endpoint_id = args.endpoint_id or cfg("VAST_ENDPOINT_ID")
    if not endpoint_id and not args.dry_run:
        endpoint_id, _ = find_ids()
    endpoint_id = endpoint_id or "<ENDPOINT_ID>"

    cmd = [
        "vastai", "update", "endpoint", str(endpoint_id),
        "--target_util", cfg("VAST_TARGET_UTIL", "0.9"),
        "--max_workers", cfg("VAST_MAX_WORKERS", "4"),
        "--inactivity_timeout", cfg("VAST_INACTIVITY_TIMEOUT", "300"),
    ]
    print("\n=== Memperbarui parameter autoscaling ===")
    if args.dry_run:
        show(cmd)
        return
    run(cmd)
    print("Parameter endpoint diperbarui.")


def cmd_status(args) -> None:
    print("\n=== Endpoints ===")
    raw = run(["vastai", "show", "endpoints", "--raw"])
    endpoints = _as_list(raw)
    if not endpoints:
        print(raw or "(tidak ada endpoint)")
    for item in endpoints:
        print(
            "  id={id}  nama={name}  state={state}".format(
                id=item.get("id"),
                name=item.get("endpoint_name") or item.get("name"),
                state=item.get("status") or item.get("endpoint_state") or "-",
            )
        )
        for key in ("url", "endpoint_url", "external_url"):
            if item.get(key):
                print(f"    URL endpoint: {item[key]}")
                print(f"    -> set VAST_ENDPOINT_URL={item[key]} di backend/.env")
        if str(item.get("endpoint_state") or "") == "stopped":
            print("    -> endpoint STOPPED; aktifkan: python scripts/vastai-setup.py activate")

    print("\n=== Workergroups ===")
    raw = run(["vastai", "show", "workergroups", "--raw"])
    groups = _as_list(raw)
    if not groups:
        print(raw or "(tidak ada workergroup)")
    for item in groups:
        print(
            "  id={id}  nama={name}  workers={workers}".format(
                id=item.get("id"),
                name=item.get("endpoint_name") or item.get("name"),
                workers=item.get("current_workers", "-"),
            )
        )


def cmd_logs(args) -> None:
    endpoint_id = args.endpoint_id or cfg("VAST_ENDPOINT_ID")
    if not endpoint_id:
        endpoint_id, _ = find_ids()
    if not endpoint_id:
        fail("endpoint id tidak ditemukan. Buat dulu: python scripts/vastai-setup.py create")
    run(["vastai", "get", "endpt-logs", str(endpoint_id), "--tail", str(args.tail)])


def cmd_benchmark(args) -> None:
    template_hash = cfg("VAST_TEMPLATE_HASH")
    if not template_hash:
        print("[i] VAST_TEMPLATE_HASH kosong: benchmark butuh template.")
        print("    Buat template dari image worker dulu, lalu isi VAST_TEMPLATE_HASH.")
        return
    cmd = ["vastai", "run", "benchmarks", "--template_hash", template_hash]
    gpus = args.gpus or cfg("VAST_BENCHMARK_GPUS", "RTX_4090,RTX_3090,RTX_A5000")
    cmd += ["--gpus", gpus]
    if args.yes:
        cmd.append("-y")
    run(cmd)


def cmd_teardown(args) -> None:
    if args.endpoint_id and args.workergroup_id:
        endpoint_id, workergroup_id = args.endpoint_id, args.workergroup_id
    else:
        endpoint_id, workergroup_id = find_ids()
    if not endpoint_id and not workergroup_id:
        fail("endpoint/workergroup tidak ditemukan.")

    print(f"Endpoint id    : {endpoint_id or '-'}")
    print(f"Workergroup id : {workergroup_id or '-'}")
    if not args.yes:
        answer = input("Hapus resource di atas? Semua worker akan dihentikan. [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Dibatalkan.")
            return

    if workergroup_id:
        run(["vastai", "delete", "workergroup", str(workergroup_id)])
    if endpoint_id:
        run(["vastai", "delete", "endpoint", str(endpoint_id)])
    print("Selesai. Billing worker berhenti.")


def main() -> int:
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Kelola Vast.ai serverless endpoint untuk Clipzi AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="tampilkan perintah tanpa menjalankan")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create", help="buat endpoint + workergroup").set_defaults(func=cmd_create)

    sub.add_parser(
        "template", help="buat template worker (image+port+env) & cetak hash-nya"
    ).set_defaults(func=cmd_template)

    p_update = sub.add_parser("update", help="perbarui parameter autoscaling")
    p_update.add_argument("--endpoint-id", help="id endpoint (default dari env/API)")
    p_update.set_defaults(func=cmd_update)

    sub.add_parser("status", help="lihat endpoint & workergroup").set_defaults(func=cmd_status)

    p_logs = sub.add_parser("logs", help="ambil log endpoint")
    p_logs.add_argument("--endpoint-id", help="id endpoint")
    p_logs.add_argument("--tail", type=int, default=100, help="jumlah baris (default 100)")
    p_logs.set_defaults(func=cmd_logs)

    p_bench = sub.add_parser("benchmark", help="benchmark template di beberapa GPU")
    p_bench.add_argument("--gpus", help="daftar GPU, mis. RTX_4090,RTX_3090")
    p_bench.add_argument("-y", "--yes", action="store_true", help="lewati konfirmasi biaya")
    p_bench.set_defaults(func=cmd_benchmark)

    p_down = sub.add_parser("teardown", help="hapus workergroup + endpoint")
    p_down.add_argument("--endpoint-id", help="id endpoint")
    p_down.add_argument("--workergroup-id", help="id workergroup")
    p_down.add_argument("-y", "--yes", action="store_true", help="tanpa konfirmasi")
    p_down.set_defaults(func=cmd_teardown)

    p_state = sub.add_parser("activate", help="aktifkan endpoint (endpoint_state=active)")
    p_state.add_argument("--endpoint-id", help="id endpoint")
    p_state.add_argument("--stop", action="store_true", help="hentikan endpoint (stopped)")
    p_state.set_defaults(func=cmd_activate)

    args = parser.parse_args()

    if shutil.which("vastai") is None and not args.dry_run:
        fail(
            "CLI `vastai` tidak ditemukan.\nInstall: pip install vastai\n"
            "Lalu: vastai set api-key <API_KEY>"
        )

    if not cfg("VAST_API_KEY") and not args.dry_run:
        print("[i] VAST_API_KEY kosong; memakai kredensial CLI (~/.config/vastai).")

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


