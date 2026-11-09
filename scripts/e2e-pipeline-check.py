#!/usr/bin/env python3
"""
Uji E2E pipeline sungguhan: DB -> download -> transkripsi -> render -> R2.

Berbeda dari `test-oneshot-offline.py` (tanpa jaringan), skrip ini memakai
layanan nyata dari `backend/.env`: PostgreSQL (Supabase), Redis, Cloudflare R2,
dan provider transkripsi (OpenRouter/Groq/OpenAI) atau whisper lokal.

    python scripts/e2e-pipeline-check.py
    python scripts/e2e-pipeline-check.py --url "https://youtu.be/xxxx" --timeout 600
    python scripts/e2e-pipeline-check.py --local-whisper      # pakai faster-whisper lokal

Yang diverifikasi: baris `tasks`/`clips` di DB, URL video/SRT/thumbnail di R2,
serta status akhir task. Biaya: kuota transkripsi provider (±$0.0000033/detik
audio di OpenRouter) + upload R2.

Butuh ffmpeg + ffprobe di PATH.
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
os.chdir(BACKEND)  # app.core.config membaca backend/.env relatif CWD
sys.path.insert(0, str(BACKEND))

EMAIL = "e2e-clipzi@example.com"


async def run(args) -> int:
    import app.models  # noqa: F401 - daftarkan mapper sebelum query
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal, engine
    from app.models.clip import Clip
    from app.models.task import Task
    from app.models.user import User
    from app.services.pipeline import run_video_pipeline

    settings = get_settings()
    print("transkripsi :", settings.TRANSCRIPTION_PROVIDER, "| model:",
          settings.TRANSCRIPTION_MODEL or settings.WHISPER_MODEL)
    print("sumber      :", args.url)

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalars().first()
        if user is None:
            user = User(email=EMAIL, name="E2E Clipzi", password_hash="x", email_verified=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print("user dibuat :", user.id)
        else:
            print("user        :", user.id)

        task = Task(
            user_id=user.id,
            source_url=args.url,
            source_type="youtube",
            target_duration_min=5,
            target_duration_max=20,
            whisper_model=args.whisper,
            output_format="mp4",
            output_resolution="1080x1920",
            fps=30,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        task_id = task.id
        print("task        :", task_id)

    started = time.time()
    try:
        result = await asyncio.wait_for(run_video_pipeline(task_id), timeout=args.timeout)
    except asyncio.TimeoutError:
        result = {"ok": False, "error": f"timeout {args.timeout:.0f}s"}
    print(f"pipeline    : {result} ({time.time() - started:.0f}s)")

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)
        clips = (
            (
                await db.execute(
                    select(Clip).where(Clip.task_id == task_id).order_by(Clip.clip_index)
                )
            )
            .scalars()
            .all()
        )
        print("status      :", task.status if task else None, "| progress:", getattr(task, "progress", None))
        if task and task.error_message:
            print("error       :", task.error_message[:300])
        print("klip        :", len(clips))
        for clip in clips:
            print(
                f"  #{clip.clip_index} {clip.start_time}-{clip.end_time} "
                f"({clip.duration:.1f}s) size={clip.file_size}"
            )
            print(f"     video : {clip.download_url}")
            print(f"     srt   : {clip.subtitle_url}")
            print(f"     thumb : {clip.thumbnail_url}")

    await engine.dispose()
    ok = bool(result.get("ok")) and len(clips) > 0
    if ok and args.expect_subtitle and any(clip.subtitle_url is None for clip in clips):
        print("PERINGATAN: ada klip tanpa subtitle (cek provider transkripsi)")
    print("\nHASIL:", "LULUS" if ok else "GAGAL")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Uji E2E pipeline Clipzi dengan layanan nyata",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url", default="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        help="video sumber (default: video 19 detik yang ada suaranya)",
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="batas tunggu detik")
    parser.add_argument("--whisper", default="small", help="model whisper untuk task (field task.whisper_model)")
    parser.add_argument(
        "--local-whisper", action="store_true",
        help="paksa TRANSCRIPTION_PROVIDER=local (butuh faster-whisper + av<15)",
    )
    parser.add_argument(
        "--expect-subtitle", action="store_true",
        help="peringatkan bila ada klip tanpa subtitle",
    )
    args = parser.parse_args()

    if args.local_whisper:
        os.environ["TRANSCRIPTION_PROVIDER"] = "local"

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
