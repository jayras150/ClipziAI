#!/usr/bin/env python3
"""
Uji E2E lewat jalur dispatch Vast (mode dari backend/.env).

Membuat user+task di DB, memanggil `submit_task()` (jalur yang dipakai API),
lalu menunggu sampai task selesai dan melaporkan klip + harga instance.

    python scripts/e2e-vast-task.py                       # pakai URL contoh di R2
    python scripts/e2e-vast-task.py --url <url-video>
    python scripts/e2e-vast-task.py --timeout 900

Mode dispatch mengikuti `VAST_DISPATCH_MODE` di backend/.env:
  oneshot -> instance dibuat per task, offer TERMURAH dipilih, lalu dihancurkan
  sdk     -> endpoint serverless (butuh worker sudah `ready`)

Biaya: ±harga instance × durasi. Dengan oneshot + offer termurah, satu task
video pendek biasanya < $0.01. Skrip juga menaksir biayanya di akhir.
"""
import argparse
import asyncio
import os
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if not (BACKEND / "app").is_dir():
    sys.exit(f"folder backend tidak ditemukan di {BACKEND}")
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

EMAIL = "e2e-clipzi@example.com"
DEFAULT_URL = "https://pub-e90798ecfe664a36b574ae3d1ec3f04d.r2.dev/e2e/source_12s.mp4"


async def run(args) -> int:
    import app.models  # noqa: F401
    from sqlalchemy import desc, select

    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal, engine
    from app.models.clip import Clip
    from app.models.task import Task
    from app.models.user import User
    from app.services.vast_worker import dispatch_mode, submit_task

    settings = get_settings()
    print("dispatch mode :", dispatch_mode())
    print("filter GPU    :", settings.VAST_GPU_FILTER)
    print("plafon harga  : $%.4f/jam" % settings.VAST_ONESHOT_MAX_PRICE)
    print("sumber        :", args.url)

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalars().first()
        if user is None:
            user = User(email=EMAIL, name="E2E Clipzi", password_hash="x", email_verified=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        task = Task(
            user_id=user.id,
            source_url=args.url,
            source_type="file",
            target_duration_min=3,
            target_duration_max=10,
            whisper_model=args.whisper,
            output_format="mp4",
            output_resolution="1080x1920",
            fps=30,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
    print("task          :", task_id)

    result = await submit_task(task_id)
    print("submit_task   :", result)
    if not result.get("queued"):
        print("DISPATCH GAGAL")
        return 1

    price = float(result.get("price_per_hour") or 0)
    started = time.time()
    last = None
    while time.time() - started < args.timeout:
        await asyncio.sleep(5)
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, task_id)
            state = (task.status.value, task.progress) if task else ("?", 0)
        if state != last:
            print(f"  [{time.time() - started:5.0f}s] {state[0]} {state[1]}%", flush=True)
            last = state
        if state[0] in {"COMPLETED", "ERROR", "CANCELLED"}:
            break

    elapsed = time.time() - started
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        clips = (
            (await db.execute(select(Clip).where(Clip.task_id == task_id).order_by(Clip.clip_index)))
            .scalars()
            .all()
        )
        print("status akhir  :", task.status.value if task else None)
        if task and task.error_message:
            print("error         :", task.error_message[:300])
        print("klip          :", len(clips))
        for clip in clips:
            print(f"  #{clip.clip_index} {clip.start_time}-{clip.end_time} ({clip.duration:.1f}s) {clip.file_size} B")
            print("     video:", clip.download_url)
            print("     srt  :", clip.subtitle_url)
    await engine.dispose()

    if price > 0:
        print(f"\nbiaya         : ${price:.4f}/jam × {elapsed/60:.1f} menit ≈ ${price * elapsed / 3600:.4f}")
    ok = bool(clips) and task is not None and task.status.value == "COMPLETED"
    if ok and price > settings.VAST_ONESHOT_MAX_PRICE > 0:
        print("PERINGATAN: harga instance melebihi plafon!")
        ok = False
    print("\nHASIL:", "LULUS" if ok else "GAGAL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uji E2E task lewat dispatch Vast (mode dari backend/.env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="video sumber (default: contoh di R2)")
    parser.add_argument("--timeout", type=float, default=900.0, help="batas tunggu detik")
    parser.add_argument("--whisper", default="small", help="model whisper untuk field task")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
