"""
Pipeline pemrosesan video — dipakai worker serverless Vast.ai dan mode inline.

Alur:
  download (yt-dlp + cookie pool) → probe ffprobe → ekstrak audio →
  transkripsi (API provider) → deteksi scene → potong + crop 9:16 →
  burn subtitle → upload ke Cloudflare R2 → simpan baris Clip.

Semua state berada di luar proses (PostgreSQL, Redis, R2), sehingga fungsi ini
aman dijalankan di worker mana pun, bahkan beberapa worker paralel sekaligus.
"""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.clip import Clip
from app.models.task import Task, TaskStatus
from app.services import cookie_store
from app.services.credit_service import CreditService
from app.services.downloader import VideoDownloader
from app.services.processor import VideoProcessor
from app.services.storage import R2Storage
from app.services.transcriber import AudioTranscriber

logger = logging.getLogger(__name__)

settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_hms(seconds: float) -> str:
    """Detik -> 'HH:MM:SS' (format kolom Clip.start_time/end_time)."""
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


async def _set_progress(db, task: Task, percent: int) -> None:
    task.progress = max(0, min(100, int(percent)))
    await db.commit()


def _select_clip_ranges(
    scenes: Sequence[Dict[str, Any]],
    min_duration: float,
    max_duration: float,
    max_clips: int,
    total_duration: float,
) -> List[Tuple[float, float]]:
    """Pilih rentang klip (start, durasi) dari hasil deteksi scene.

    Prioritas: scene yang durasinya memenuhi target. Kalau tidak ada scene yang
    cocok (atau scene detection gagal), bagi video secara merata.
    """
    ranges: List[Tuple[float, float]] = []

    for scene in scenes:
        start = float(scene.get("start") or 0)
        end = float(scene.get("end") or 0)
        duration = end - start
        if duration < min_duration:
            continue
        clip_duration = min(duration, max_duration)
        ranges.append((round(start, 2), round(clip_duration, 2)))
        if len(ranges) >= max_clips:
            break

    if ranges or total_duration <= 0:
        return ranges

    # Fallback: bagi durasi video menjadi beberapa bagian merata
    step = total_duration / max(1, max_clips)
    clip_duration = min(max_duration, max(min_duration, step))
    for index in range(max_clips):
        start = round(index * step, 2)
        remaining = total_duration - start
        if remaining < 1:
            break
        ranges.append((start, round(min(clip_duration, remaining), 2)))

    return ranges


def _slice_segments(
    segments: Sequence[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
) -> List[Dict[str, Any]]:
    """Ambil segmen transkripsi di dalam rentang klip dan geser waktunya ke 0."""
    sliced: List[Dict[str, Any]] = []
    for segment in segments:
        seg_start = float(segment.get("start") or 0)
        seg_end = float(segment.get("end") or 0)
        if seg_end <= clip_start or seg_start >= clip_end:
            continue
        sliced.append(
            {
                **segment,
                "start": max(0.0, seg_start - clip_start),
                "end": max(0.0, min(clip_end, seg_end) - clip_start),
            }
        )
    return sliced


async def run_video_pipeline(task_id: UUID) -> Dict[str, Any]:
    """Jalankan seluruh pipeline untuk satu task.

    Mengembalikan dict ringkas: {"ok": bool, "clips": int, "error": str|None}.
    Status & progress task selalu di-update di PostgreSQL agar frontend bisa
    melakukan polling tanpa bergantung pada worker yang menjalankannya.
    """
    async with AsyncSessionLocal() as db:
        task: Optional[Task] = await db.get(Task, task_id)
        if task is None:
            logger.warning("Pipeline: task %s tidak ditemukan", task_id)
            return {"ok": False, "clips": 0, "error": "task not found"}

        if task.status == TaskStatus.COMPLETED:
            return {"ok": True, "clips": task.total_clips or 0, "error": None}

        task.status = TaskStatus.PROCESSING
        task.progress = 1
        task.error_message = None
        await db.commit()

        work_dir = Path(settings.WORKER_WORK_DIR) / str(task.id)
        work_dir.mkdir(parents=True, exist_ok=True)

        downloader = VideoDownloader(str(work_dir / "input"))
        processor = VideoProcessor(str(work_dir))
        transcriber = AudioTranscriber()
        storage = R2Storage()

        options: Dict[str, Any] = task.editing_options or {}
        burn_subtitle = bool(options.get("burn_subtitle", True))
        max_clips = int(options.get("max_clips", 3) or 3)
        min_duration = float(task.target_duration_min or 30)
        max_duration = float(task.target_duration_max or 60)
        # ---------- Fase 1: editing manual ----------
        manual_start = options.get("start_time")
        manual_end = options.get("end_time")
        aspect_ratio = str(options.get("aspect_ratio", "9:16"))
        caption_text = options.get("caption_text")
        speed = float(options.get("speed", 1.0) or 1.0)

        try:
            # 1) Unduh sumber (memakai cookie pool bila ada)
            await _set_progress(db, task, 5)
            acquired = await cookie_store.acquire(db)
            cookie, cookiefile = acquired if acquired else (None, None)
            try:
                video_path = await downloader.download_video(
                    task.source_url, "source", cookies_path=cookiefile
                )
                if cookie is not None:
                    await cookie_store.report_success(db, cookie)
            except Exception as exc:
                if cookie is not None:
                    await cookie_store.report_failure(db, cookie, str(exc))
                raise
            finally:
                # Simpan balik token yang mungkin sudah dirotasi yt-dlp
                if cookie is not None:
                    await cookie_store.sync_back(db, cookie)

            # 2) Probe metadata
            info = await processor.get_video_info(video_path)
            task.original_duration = info.get("duration")
            await db.commit()
            await _set_progress(db, task, 15)

            # 3) Ekstrak audio + transkripsi (API provider)
            segments: List[Dict[str, Any]] = []
            try:
                audio_path = await processor.extract_audio(
                    video_path, str(work_dir / "audio.mp3")
                )
                result = await transcriber.transcribe(audio_path)
                segments = list(result.get("segments") or [])
                logger.info(
                    "Pipeline: %s segmen transkripsi untuk task %s", len(segments), task.id
                )
            except Exception as exc:
                # Transkripsi gagal bukan alasan menggagalkan task; klip tetap
                # dibuat, hanya tanpa subtitle.
                logger.warning("Transkripsi gagal untuk task %s: %s", task.id, exc)
            await _set_progress(db, task, 35)

            # 4) Tentukan rentang klip — manual trim prioritas atas scene detection
            total_duration = float(info.get("duration") or 0)
            if manual_start is not None:
                start = float(manual_start)
                end = float(manual_end) if manual_end is not None else total_duration
                if end <= start:
                    end = start + min(max_duration, max(total_duration - start, 1))
                end = min(end, total_duration)
                ranges = [(round(start, 2), round(end - start, 2))]
                logger.info(
                    "Pipeline: trim manual task %s -> %.2f-%.2f detik", task.id, start, end
                )
            else:
                scenes = await processor.detect_scenes(video_path)
                ranges = _select_clip_ranges(
                    scenes,
                    min_duration,
                    max_duration,
                    max_clips,
                    total_duration,
                )
                if not ranges:
                    raise RuntimeError(
                        "Tidak ada rentang klip yang bisa diproses dari video ini"
                    )

            # 5) Render tiap klip
            rendered: List[Dict[str, Any]] = []
            total = len(ranges)
            for index, (start, duration) in enumerate(ranges, 1):
                raw_clip = str(work_dir / f"clip_{index:02d}_raw.mp4")
                await processor.smart_crop_aspect(
                    video_path,
                    raw_clip,
                    start_time=start,
                    duration=duration,
                    aspect_ratio=aspect_ratio,
                )

                final_clip = raw_clip
                subtitle_url: Optional[str] = None
                if burn_subtitle and segments:
                    sliced = _slice_segments(segments, start, start + duration)
                    if sliced:
                        srt_path = str(work_dir / f"clip_{index:02d}.srt")
                        transcriber.generate_srt(sliced, srt_path)

                        # Burn subtitle bersifat opsional: kalau ffmpeg gagal
                        # (font/filter/path), klip tetap dikirim tanpa subtitle
                        # alih-alih menggagalkan seluruh task.
                        burned = str(work_dir / f"clip_{index:02d}_sub.mp4")
                        try:
                            await processor.burn_subtitle(raw_clip, srt_path, burned)
                            final_clip = burned
                        except Exception as exc:
                            logger.warning(
                                "Burn subtitle gagal (task %s klip %s): %s — "
                                "klip dikirim tanpa subtitle",
                                task.id,
                                index,
                                exc,
                            )

                        try:
                            srt_key = storage.generate_object_key(
                                str(task.user_id),
                                f"clip_{index:02d}.srt",
                                folder=f"clips/{task.id}",
                            )
                            subtitle_url = storage.upload_bytes(
                                Path(srt_path).read_bytes(), srt_key, "text/plain"
                            )
                        except Exception as exc:
                            logger.warning(
                                "Upload SRT gagal (task %s klip %s): %s", task.id, index, exc
                            )

                # ---------- Fase 1: caption teks + kecepatan ----------
                if caption_text:
                    captioned = str(work_dir / f"clip_{index:02d}_caption.mp4")
                    try:
                        await processor.add_text_overlay(
                            final_clip,
                            captioned,
                            caption_text,
                            font_size=26,
                            font_color="white",
                            x="(w-text_w)/2",
                            y="h-text_h-40",
                        )
                        final_clip = captioned
                    except Exception as exc:
                        logger.warning(
                            "Caption gagal (task %s klip %s): %s", task.id, index, exc
                        )
                if speed != 1.0:
                    sped = str(work_dir / f"clip_{index:02d}_speed.mp4")
                    try:
                        await processor.change_speed(final_clip, sped, speed)
                        final_clip = sped
                    except Exception as exc:
                        logger.warning(
                            "Ubah kecepatan gagal (task %s klip %s): %s",
                            task.id,
                            index,
                            exc,
                        )

                clip_key = storage.generate_object_key(
                    str(task.user_id), f"clip_{index:02d}.mp4", folder=f"clips/{task.id}"
                )
                download_url = storage.upload_file(final_clip, clip_key, "video/mp4")

                thumbnail_url: Optional[str] = None
                thumb_path = await processor.extract_thumbnail(
                    final_clip, str(work_dir / f"clip_{index:02d}.jpg")
                )
                if thumb_path:
                    thumb_key = storage.generate_object_key(
                        str(task.user_id),
                        f"clip_{index:02d}.jpg",
                        folder=f"thumbs/{task.id}",
                    )
                    thumbnail_url = storage.upload_file(thumb_path, thumb_key, "image/jpeg")

                rendered.append(
                    {
                        "start": start,
                        "duration": duration,
                        "download_url": download_url,
                        "subtitle_url": subtitle_url,
                        "thumbnail_url": thumbnail_url,
                        "file_size": Path(final_clip).stat().st_size,
                    }
                )
                await _set_progress(db, task, 35 + int(55 * index / max(1, total)))

            # 6) Simpan klip & tandai task selesai
            for index, clip in enumerate(rendered, 1):
                db.add(
                    Clip(
                        task_id=task.id,
                        clip_index=index,
                        start_time=_fmt_hms(clip["start"]),
                        end_time=_fmt_hms(clip["start"] + clip["duration"]),
                        duration=clip["duration"],
                        title=f"Clip {index} - {task.source_type}",
                        download_url=clip["download_url"],
                        subtitle_url=clip["subtitle_url"],
                        thumbnail_url=clip["thumbnail_url"],
                        file_size=clip["file_size"],
                        editing_applied=[
                            k
                            for k, v in options.items()
                            if v is not None and v is not False and v != ""
                        ],
                    )
                )

            task.total_clips = len(rendered)
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = _now()
            await db.commit()

            # 7) Potong kredit (1 per klip). Gagal potong tidak membatalkan hasil.
            try:
                await CreditService.deduct_credits(
                    db,
                    str(task.user_id),
                    float(len(rendered)),
                    {"reason": "video_processing", "clips": len(rendered)},
                    task_id=str(task.id),
                )
                task.credits_spent = len(rendered)
                await db.commit()
            except Exception as exc:
                logger.warning("Gagal memotong kredit task %s: %s", task.id, exc)

            logger.info("Pipeline selesai: task %s -> %s klip", task.id, len(rendered))
            return {"ok": True, "clips": len(rendered), "error": None}

        except Exception as exc:
            logger.exception("Pipeline gagal untuk task %s", task.id)
            task.status = TaskStatus.ERROR
            task.error_message = str(exc)[:2000]
            await db.commit()
            return {"ok": False, "clips": 0, "error": str(exc)}

        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


