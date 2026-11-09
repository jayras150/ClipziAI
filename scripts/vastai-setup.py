#!/usr/bin/env python3
"""
Kelola endpoint + workergroup Vast.ai Serverless untuk Clipzi AI.

Pemakaian:
    python scripts/vastai-setup.py template    # buat template worker -> dapat hash
    python scripts/vastai-setup.py retemplate  # arahkan workergroup ke template (hash baru)
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
import ast
import json
import os
import re
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
    """Susun launch_args: worker role + port PyWorker + image + disk."""
    parts = []
    image = cfg("VAST_WORKER_IMAGE")
    if image:
        parts.append(f"--image {image}")
    parts.append("--env '-e CLIPZI_ROLE=worker'")
    # WORKER_PORT = port PyWorker (yang dilaporkan `ready` ke router Vast).
    parts.append("--env '-e WORKER_PORT=8000'")
    # Service pipeline berjalan di localhost; tidak diekspos ke host.
    parts.append("--env '-e MODEL_SERVER_PORT=18000'")
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

    PENTING: workergroup yang memakai `--template_hash` mengambil filter offer
    DARI TEMPLATE (bukan dari workergroup), sehingga tanpa `--search_params` di
    sini engine bisa memilih GPU mahal (pernah kejadian: RTX 5090/3090).
    """
    cmd = [
        "vastai", "create", "template",
        "--name", cfg("VAST_TEMPLATE_NAME", "clipzi-worker"),
        "--image", cfg("VAST_WORKER_IMAGE") or "<user>/clipzi-backend:1.0.0",
        "--env", "-p 8000:8000 -e CLIPZI_ROLE=worker -e WORKER_PORT=8000 -e MODEL_SERVER_PORT=18000",
        "--disk_space", cfg("VAST_WORKER_DISK", "40"),
        "--desc", "Clipzi AI GPU worker (FastAPI + ffmpeg + yt-dlp)",
    ]
    search_params = cfg("VAST_GPU_FILTER")
    if search_params:
        cmd += ["--search_params", search_params]
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


def parse_created_template(output: str) -> dict:
    """Ambil data template hasil `vastai create template`.

    CLI mencetak JSON bila dipanggil dengan `--raw`. Tanpa `--raw`, keluarannya
    berbentuk ``New Template: {'name': ..., 'hash_id': ..., 'id': ...}`` (repr
    Python), sehingga perlu di-parse terpisah. Template privat TIDAK muncul di
    `search templates`, jadi parsing keluaran create adalah cara yang andal.
    """
    text = (output or "").strip()
    if not text:
        return {}
    try:  # jalur utama: --raw -> JSON
        data = json.loads(text)
        if isinstance(data, list):
            data = data[0] if data else {}
        if isinstance(data, dict) and (data.get("hash_id") or data.get("id")):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)  # jalur cadangan: repr Python
    if match:
        try:
            data = ast.literal_eval(match.group(0))
        except (ValueError, SyntaxError):
            return {}
        if isinstance(data, dict):
            return data
    return {}



def cmd_activate(args) -> None:
    """Ubah endpoint_state: active | suspended | stopped.

    Catatan penting: workergroup sendiri TIDAK punya perintah start/stop di CLI
    Vast (`vastai update workergroup` hanya mengubah template/search/launch).
    Yang mengendalikan hidup-matinya worker adalah endpoint:

      active    -> engine menaikkan/menurunkan worker sesuai trafik
      suspended -> engine berhenti mengelola, worker yang sudah siap TETAP aktif
                   (masih ditagih GPU)
      stopped   -> semua worker jadi inactive (GPU tidak ditagih; storage tetap)
    """
    endpoint_id = args.endpoint_id or cfg("VAST_ENDPOINT_ID")
    if not endpoint_id:
        existing = find_endpoint_by_name()
        endpoint_id = str(existing.get("id")) if existing else ""
    if not endpoint_id:
        fail("endpoint tidak ditemukan. Buat dulu: python scripts/vastai-setup.py create")

    if args.state:
        state = args.state
    elif args.stop:
        state = "stopped"
    elif args.suspend:
        state = "suspended"
    else:
        state = "active"

    cmd = ["vastai", "update", "endpoint", str(endpoint_id), "--endpoint_state", state]
    print(f"\n=== Set endpoint {endpoint_id} -> {state} ===")
    if args.dry_run:
        show(cmd)
        return
    run(cmd)
    print(f"Endpoint {endpoint_id} sekarang: {state}")
    if state == "stopped":
        print("Worker menjadi inactive: GPU tidak ditagih (storage/bandwidth tetap).")
    elif state == "suspended":
        print("Engine berhenti mengelola; worker yang sudah Ready MASIH ditagih GPU.")
        print("Gunakan 'activate --stop' bila ingin GPU benar-benar berhenti.")


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

    cmd = template_create_cmd() + ["--raw"]
    print(f"\n=== Membuat template '{cfg('VAST_TEMPLATE_NAME', 'clipzi-worker')}' ===")
    if args.dry_run:
        show(cmd)
        return

    created_output = run(cmd)
    created = parse_created_template(created_output)
    if created.get("hash_id"):
        template_hash = created["hash_id"]
        print(f"  nama : {created.get('name')}")
        print(f"  image: {created.get('image')}")
        print(f"  env  : {created.get('env')}")
        print(f"  hash : {template_hash}")
        print(f"  id   : {created.get('id')}")
        print("\nTambahkan ke backend/.env:")
        print(f"  VAST_TEMPLATE_HASH={template_hash}")
        print("\nLalu arahkan workergroup ke template ini (kalau workergroup sudah ada):")
        print(f"  python scripts/vastai-setup.py retemplate --hash {template_hash}")
        return

    print(created_output or "(tanpa keluaran)")
    name = cfg("VAST_TEMPLATE_NAME", "clipzi-worker")
    print("\n=== Hash tidak terbaca dari keluaran create; mencoba search templates ===")
    # CLI tidak punya `show templates`; yang benar `search templates`.
    # Field hash bernama `hash_id`. Template privat biasanya TIDAK muncul di sini.
    matches = [
        item
        for item in _as_list(run(["vastai", "search", "templates", "--raw"]))
        if str(item.get("name")) == name
    ]
    matches.sort(key=lambda item: item.get("id") or 0, reverse=True)

    if matches:
        item = matches[0]
        template_hash = item.get("hash_id") or item.get("hash") or item.get("id")
        print(f"  nama : {name}")
        print(f"  hash : {template_hash}")
        print(f"  id   : {item.get('id')}")
        print("\nTambahkan ke backend/.env:")
        print(f"  VAST_TEMPLATE_HASH={template_hash}")
        print("\nLalu arahkan workergroup ke template ini:")
        print(f"  python scripts/vastai-setup.py retemplate --hash {template_hash}")
        return

    print("Template dibuat, tetapi hash tidak ditemukan otomatis.")
    print("Kemungkinan template masih privat sehingga tidak muncul di pencarian.")
    print("Alternatif: buka cloud.vast.ai/templates dan salin hash dari kartu template,")
    print("atau pakai mode tanpa template: isi VAST_WORKER_IMAGE saja.")


def repoint_workergroup(template_hash: str) -> None:
    """Arahkan workergroup yang sudah ada ke template (image/port/env) baru.

    `vastai update endpoint` hanya mengubah autoscaling; template & launch args
    ada di workergroup. Tanpa langkah ini, workergroup tetap memakai template
    lama sehingga worker yang boot bukan image yang kita harapkan (penyebab
    worker tidak pernah `ready`).

    PENTING: `--template_hash` membuat Vast meng-infer search query dari template,
    sehingga filter GPU/harga dari VAST_GPU_FILTER HILANG (worker bisa jatuh di
    GPU mahal). Karena itu filter selalu dikirim ulang di sini.
    """
    endpoint_id = cfg("VAST_ENDPOINT_ID")
    workergroup_id = cfg("VAST_WORKERGROUP_ID")
    if not endpoint_id or not workergroup_id:
        found_endpoint, found_group = find_ids()
        endpoint_id = endpoint_id or (str(found_endpoint) if found_endpoint else "")
        workergroup_id = workergroup_id or (str(found_group) if found_group else "")
    if not workergroup_id:
        fail("workergroup tidak ditemukan. Buat dulu: python scripts/vastai-setup.py create")

    cmd = [
        "vastai", "update", "workergroup", str(workergroup_id),
        "--template_hash", template_hash,
        "--launch_args", f"--disk {cfg('VAST_WORKER_DISK', '40')}",
    ]
    search_params = cfg("VAST_GPU_FILTER")
    if search_params:
        cmd += ["--search_params", search_params]
    if endpoint_id:
        cmd += ["--endpoint_id", str(endpoint_id)]
    run(cmd)
    print(f"Workergroup {workergroup_id} sekarang memakai template {template_hash}.")
    print("Filter GPU/harga diterapkan ulang dari VAST_GPU_FILTER:")
    print(f"  {search_params or '(kosong — worker bisa jatuh di GPU mahal!)'}")


def cmd_cheapest(args) -> None:
    """Pakai offer TERMURAH saat ini: hitung harga minimum lalu paku cap-nya.

    Autoscaler Vast TIDAK mengurutkan offer berdasarkan harga, jadi filter
    `dph_total<X` yang longgar bisa menghasilkan instance mahal. Perintah ini
    mencari harga minimum pasar untuk filter yang dipakai, lalu menulis filter
    dengan `dph_total<=<min+margin>` sehingga hanya offer termurah yang lolos.
    """
    base_filter = cfg("VAST_GPU_FILTER")
    parts = [p for p in base_filter.split() if not p.startswith("dph_total")]
    query = " ".join(parts)
    if not query:
        fail("VAST_GPU_FILTER kosong; isi dulu filter GPU Anda di backend/.env")

    print("\n=== Mencari offer termurah ===")
    print(f"> filter: {query}")
    raw = run(["vastai", "search", "offers", query, "--raw"])
    try:
        offers = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        fail(f"keluaran search offers tidak bisa dibaca: {raw[:200]}")

    if not offers:
        fail(
            "tidak ada offer yang cocok dengan filter:\n"
            f"  {query}\n"
            "Catatan: `gpu_ram` di Vast memakai satuan GB (mis. gpu_ram>=4),\n"
            "bukan MB (gpu_ram>=4000 menghasilkan 0 offer)."
        )

    offers = [o for o in offers if float(o.get("dph_total") or 0) > 0]
    offers.sort(key=lambda o: float(o["dph_total"]))
    best = offers[0]
    price = float(best["dph_total"])
    cap = round(price + float(args.margin), 4)
    print(
        f"termurah: {best.get('gpu_name')} ${price:.4f}/jam "
        f"(vram {round(float(best.get('gpu_ram') or 0) / 1024)} GB) -> cap ${cap:.4f}"
    )

    search_params = f"{query} dph_total<={cap}"
    endpoint_id = cfg("VAST_ENDPOINT_ID")
    workergroup_id = cfg("VAST_WORKERGROUP_ID")
    if not endpoint_id or not workergroup_id:
        found_endpoint, found_group = find_ids()
        endpoint_id = endpoint_id or (str(found_endpoint) if found_endpoint else "")
        workergroup_id = workergroup_id or (str(found_group) if found_group else "")
    if not workergroup_id:
        fail("workergroup tidak ditemukan. Buat dulu: python scripts/vastai-setup.py create")

    cmd = [
        "vastai", "update", "workergroup", str(workergroup_id),
        "--search_params", search_params,
        "--launch_args", f"--disk {cfg('VAST_WORKER_DISK', '40')}",
    ]
    template_hash = cfg("VAST_TEMPLATE_HASH")
    if template_hash:
        cmd += ["--template_hash", template_hash]
    if endpoint_id:
        cmd += ["--endpoint_id", str(endpoint_id)]

    if args.dry_run:
        show(cmd)
    else:
        run(cmd)
        print(f"Workergroup {workergroup_id} dipaku ke offer termurah (cap ${cap:.4f}/jam).")
    print("\nAgar konsisten saat template dibuat ulang, set di backend/.env:")
    print(f"  VAST_GPU_FILTER={search_params}")


def cmd_retemplate(args) -> None:
    template_hash = args.hash or cfg("VAST_TEMPLATE_HASH")
    if not template_hash and not args.dry_run:
        fail(
            "hash template kosong.\n"
            "Buat template dulu: python scripts/vastai-setup.py template\n"
            "lalu jalankan: python scripts/vastai-setup.py retemplate --hash <hash>"
        )
    template_hash = template_hash or "<TEMPLATE_HASH>"
    print("\n=== Mengarahkan workergroup ke template worker ===")
    if args.dry_run:
        endpoint_id = cfg("VAST_ENDPOINT_ID") or "<ENDPOINT_ID>"
        workergroup_id = cfg("VAST_WORKERGROUP_ID") or "<WORKERGROUP_ID>"
        show([
            "vastai", "update", "workergroup", str(workergroup_id),
            "--template_hash", template_hash,
            "--launch_args", f"--disk {cfg('VAST_WORKER_DISK', '40')}",
            "--endpoint_id", str(endpoint_id),
        ])
        return
    repoint_workergroup(template_hash)



def cmd_update(args) -> None:
    endpoint_id = args.endpoint_id or cfg("VAST_ENDPOINT_ID")
    if not endpoint_id and not args.dry_run:
        endpoint_id, _ = find_ids()
    endpoint_id = endpoint_id or "<ENDPOINT_ID>"

    cmd = [
        "vastai", "update", "endpoint", str(endpoint_id),
        "--target_util", str(args.target_util or cfg("VAST_TARGET_UTIL", "0.9")),
        "--max_workers", str(args.max_workers if args.max_workers is not None else cfg("VAST_MAX_WORKERS", "4")),
        "--inactivity_timeout", str(
            args.inactivity_timeout if args.inactivity_timeout is not None
            else cfg("VAST_INACTIVITY_TIMEOUT", "300")
        ),
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

    p_retpl = sub.add_parser(
        "retemplate", help="arahkan workergroup yang sudah ada ke template worker"
    )
    p_retpl.add_argument("--hash", help="hash template (default: VAST_TEMPLATE_HASH)")
    p_retpl.set_defaults(func=cmd_retemplate)

    p_cheap = sub.add_parser(
        "cheapest", help="paku workergroup ke offer TERMURAH saat ini (hitung cap harga)"
    )
    p_cheap.add_argument(
        "--margin", type=float, default=0.001, help="toleransi di atas harga termurah (default 0.001)"
    )
    p_cheap.set_defaults(func=cmd_cheapest)

    p_update = sub.add_parser("update", help="perbarui parameter autoscaling")
    p_update.add_argument("--endpoint-id", help="id endpoint (default dari env/API)")
    p_update.add_argument("--max-workers", type=int, help="batas worker (0 = tidak ada worker)")
    p_update.add_argument("--inactivity-timeout", type=int, help="detik idle sebelum scale-to-zero")
    p_update.add_argument("--target-util", type=float, help="target utilisasi (0-1)")
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

    p_state = sub.add_parser(
        "activate", help="ubah endpoint_state (active/suspended/stopped)"
    )
    p_state.add_argument("--endpoint-id", help="id endpoint")
    p_state.add_argument(
        "--state", choices=["active", "suspended", "stopped"], help="state tujuan (default active)"
    )
    p_state.add_argument("--stop", action="store_true", help="alias untuk --state stopped")
    p_state.add_argument("--suspend", action="store_true", help="alias untuk --state suspended")
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


