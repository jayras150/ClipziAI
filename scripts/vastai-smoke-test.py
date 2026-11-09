#!/usr/bin/env python3
"""
Smoke test endpoint Vast.ai serverless milik Clipzi (`clipzyai`).

Tujuan: membuktikan worker benar-benar sampai status `ready` dan bisa melayani
request. Ini yang membedakan "endpoint aktif" dari "endpoint bisa dipakai" —
endpoint bisa `active` tapi worker berhenti di `model_loading` (mis. karena image
worker tidak memakai PyWorker), sehingga request gagal dengan
`failed to find rdy worker`.

    python scripts/vastai-smoke-test.py                # hanya status (gratis)
    python scripts/vastai-smoke-test.py --send         # kirim 1 request /health (memicu cold start)
    python scripts/vastai-smoke-test.py --send --timeout 600

Biaya: tanpa `--send` tidak ada biaya. Dengan `--send`, worker GPU hidup selama
cold start + `inactivity_timeout` (beberapa sen). Jalankan
`python scripts/vastai-setup.py activate --stop` untuk memastikan GPU mati.

Membaca kredensial dari backend/.env (VAST_API_KEY, VAST_ENDPOINT_NAME).
"""
import argparse
import asyncio
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "backend" / ".env"


def load_env() -> None:
    if not ENV_FILE.is_file():
        sys.exit(f"backend/.env tidak ditemukan di {ENV_FILE}")
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cfg(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


async def sdk_call(factory, attempts: int = 5, delay: float = 3.0):
    """Panggil SDK dengan retry untuk HTTP 429 (Vast membatasi ~1 req/detik)."""
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - 429 / gangguan jaringan sesaat
            last = exc
            if "429" not in str(exc) and "TooManyRequests" not in str(exc):
                raise
            if attempt == attempts:
                break
            print(f"  (429 rate limit, coba lagi {attempt}/{attempts - 1} ...)", flush=True)
            await asyncio.sleep(delay)
    assert last is not None
    raise last


async def poll_workers(client, endpoint, deadline: float, stop: asyncio.Event) -> None:
    """Cetak perubahan status worker (loading -> model_loading -> ready)."""
    last = None
    while not stop.is_set() and time.monotonic() < deadline:
        try:
            workers = await sdk_call(lambda: client.get_endpoint_workers(endpoint))
            snapshot = [(w.id, getattr(w, "status", None)) for w in workers]
            if snapshot != last:
                print(f"  [{time.strftime('%H:%M:%S')}] workers={snapshot}", flush=True)
                last = snapshot
        except Exception as exc:  # noqa: BLE001 - biarkan polling lanjut
            print(f"  poll: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass


async def main(args: argparse.Namespace) -> int:
    from vastai import Serverless

    name = cfg("VAST_ENDPOINT_NAME", "clipzyai")
    client = Serverless(api_key=cfg("VAST_API_KEY"))
    try:
        endpoint = await client.get_endpoint(name=name)
        print(f"endpoint '{name}': objek {type(endpoint).__name__}")

        workers = await sdk_call(lambda: client.get_endpoint_workers(endpoint))
        statuses = [(w.id, getattr(w, "status", None)) for w in workers]
        print(f"workers: {statuses or '(belum ada / scale-to-zero)'}")
        if any(status == "ready" for _, status in statuses):
            print("SUDAH ADA worker ready — endpoint siap menerima request.")
        else:
            print("Belum ada worker `ready` (normal kalau scale-to-zero).")

        if not args.send:
            print("\nSelesai (tanpa --send: tidak ada request, tidak ada biaya GPU).")
            return 0

        deadline = time.monotonic() + args.timeout
        stop = asyncio.Event()
        poller = asyncio.create_task(poll_workers(client, endpoint, deadline, stop))

        print(f"\nMengirim request GET '{args.route}' (memicu cold start) ...")
        started = time.monotonic()
        try:
            request = client.queue_endpoint_request(
                endpoint,
                args.route,
                {},
                cost=100,
                timeout=args.timeout,
                worker_timeout=args.timeout,
                retry=True,
            )
            result = await request
            elapsed = time.monotonic() - started
            text = str(result)
            print(f"\nOK setelah {elapsed:.0f} detik: {text[:400]}")
            return 0
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - started
            print(f"\nGAGAL setelah {elapsed:.0f} detik: {type(exc).__name__}: {exc}")
            print(
                "Petunjuk: cek `python scripts/vastai-setup.py logs --tail 50`.\n"
                "Pesan 'failed to find rdy worker' = worker tidak pernah ready:\n"
                "  - image worker harus memakai PyWorker (CLIPZI_ROLE=worker)\n"
                "  - template harus mengekspos port PyWorker (-p 8000:8000, WORKER_PORT=8000)\n"
                "  - workergroup harus memakai template terbaru (lihat `retemplate`)"
            )
            return 1
        finally:
            stop.set()
            await asyncio.gather(poller, return_exceptions=True)
            workers = await sdk_call(lambda: client.get_endpoint_workers(endpoint))
            print(
                "workers setelah request:",
                [(w.id, getattr(w, "status", None)) for w in workers],
            )
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Smoke test endpoint Vast.ai serverless Clipzi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--send", action="store_true", help="kirim 1 request (memicu cold start & biaya)")
    parser.add_argument("--route", default="/health", help="route worker (default /health)")
    parser.add_argument("--timeout", type=float, default=420.0, help="batas tunggu detik")
    args = parser.parse_args()

    load_env()
    if not cfg("VAST_API_KEY"):
        sys.exit("VAST_API_KEY kosong di backend/.env")
    sys.exit(asyncio.run(main(args)))
