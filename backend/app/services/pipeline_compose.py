"""
Pipeline "compose" & "split" — editing atas klip yang SUDAH jadi.

Worker Vast.ai membaca klip hasil task sebelumnya dari R2, menggabungkan (dengan
transisi) atau memotongnya, lalu mengunggah hasil baru. Tidak ada unduhan ulang
video sumber sehingga jauh lebih cepat daripada task biasa.

Mode dipilih lewat task.editing_options:
    {"mode": "compose", "clip_ids": [...], "transition": "fade", "music_url": ...}
    {"mode": "split",   "clip_id": "...", "at_time": 5.2}
"""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.clip import Clip
from app.models.task import Task, TaskStatus
from app.services.credit_service import CreditService
from app.services.pipeline import _download_asset, _ext_from_url, _fmt_hms
from app.services.platform_watermark import apply_platform_watermark
from app.services.processor import VideoProcessor
from app.services.storage_registry import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _set_progress(db, task: Task, percent: int) -> None:
    task.progress = max(0, min(100, int(percent)))
    await db.commit()


async def _load_source_clips(db, task: Task, clip_ids: List[str]) -> List[Clip]:
    """Ambil klip milik user yang sama, urut sesuai clip_ids."""
    parsed: List[UUID] = []
    for raw in clip_ids:
        try:
            parsed.append(UUID(str(raw)))
        except (ValueError, AttributeError):
            continue
        continue
    if not parsed:
        raise RuntimeError("clip_ids is empty or invalid")

    result = await db.execute(
        select(Clip).where(
            Clip.id.in_(parsed),
            Clip.task_id.in_(select(Task.id).where(Task.user_id == task.user_id)),
        )
    )
    found = {str(clip.id): clip for clip in result.scalars().all()}
    ordered = [found[str(cid)] for cid in parsed if str(cid) in found]
    if not ordered:
        raise RuntimeError("No valid clips found for this user")
    return ordered


async def run_compose_pipeline(task_id: UUID) -> Dict[str, Any]:
    """Gabungkan beberapa klip (opsional transisi + musik + watermark)."""
    async with AsyncSessionLocal() as db:
        task: Optional[Task] = await db.get(Task, task_id)
        if task is None:
            return {"ok": False, "clips": 0, "error": "task not found"}

        options: Dict[str, Any] = task.editing_options or {}
        work_dir = Path(settings.WORKER_WORK_DIR) / str(task.id)
        work_dir.mkdir(parents=True, exist_ok=True)
        processor = VideoProcessor(str(work_dir))
        storage = get_storage()

        task.status = TaskStatus.PROCESSING
        task.progress = 5
        task.error_message = None
        await db.commit()

        try:
            clips = await _load_source_clips(db, task, options.get("clip_ids") or [])
            await _set_progress(db, task, 20)

            local_paths: List[str] = []
            for index, clip in enumerate(clips, 1):
                if not clip.download_url:
                    continue
                dest = str(work_dir / f"part_{index:02d}.{_ext_from_url(clip.download_url)}")
                await _download_asset(clip.download_url, dest)
                local_paths.append(dest)
            if not local_paths:
                raise RuntimeError("None of the source clips has a download_url")
            await _set_progress(db, task, 45)

            width, height = processor._dimensions_for_ratio(
                str(options.get("aspect_ratio") or "9:16")
            )
            joined = str(work_dir / "joined.mp4")
            await processor.concat_with_transition(
                local_paths,
                joined,
                transition=str(options.get("transition") or "none"),
                transition_duration=float(options.get("transition_duration") or 0.4),
                width=width,
                height=height,
            )
            await _set_progress(db, task, 70)

            final_clip = joined
            music_url = options.get("music_url")
            if music_url:
                try:
                    music_path = str(work_dir / f"music.{_ext_from_url(music_url, 'mp3')}")
                    await _download_asset(str(music_url), music_path)
                    mixed = str(work_dir / "mixed.mp4")
                    await processor.mix_music(
                        final_clip, music_path, mixed,
                        volume=float(options.get("music_volume") or 0.22),
                        ducking=bool(options.get("music_ducking", True)),
                    )
                    final_clip = mixed
                except Exception as exc:
                    logger.warning("Mix musik gagal (task %s): %s", task.id, exc)


            watermark_url = options.get("watermark_url")
            if watermark_url:
                try:
                    wm_path = str(work_dir / f"wm.{_ext_from_url(watermark_url, 'png')}")
                    await _download_asset(str(watermark_url), wm_path)
                    stamped = str(work_dir / "stamped.mp4")
                    await processor.overlay_image(
                        final_clip, wm_path, stamped,
                        position=str(options.get("watermark_position") or "bottom-right"),
                        scale=float(options.get("watermark_scale") or 0.16),
                        opacity=float(options.get("watermark_opacity") or 0.85),
                    )
                    final_clip = stamped
                except Exception as exc:
                    logger.warning("Watermark gagal (task %s): %s", task.id, exc)

            # Watermark platform juga wajib di jalur compose/split — kalau tidak,
            # user free bisa menghapus watermark dengan menggabungkan klip.
            brand_applied = False
            try:
                branded = str(work_dir / "branded.mp4")
                brand_source, brand_applied = await apply_platform_watermark(
                    processor, task, final_clip, branded, work_dir
                )
                if brand_applied:
                    final_clip = brand_source
            except Exception as exc:
                logger.warning("Watermark platform gagal (task %s): %s", task.id, exc)

            await _set_progress(db, task, 85)

            info = await processor.get_video_info(final_clip)
            duration = float(info.get("duration") or 0)
            download_url = storage.upload_file(
                final_clip,
                storage.generate_object_key(
                    str(task.user_id), "compose.mp4", folder=f"clips/{task.id}"
                ),
                "video/mp4",
            )

            thumbnail_url = None
            thumb_path = await processor.extract_thumbnail(
                final_clip, str(work_dir / "thumb.jpg")
            )
            if thumb_path:
                thumbnail_url = storage.upload_file(
                    thumb_path,
                    storage.generate_object_key(
                        str(task.user_id), "thumb.jpg", folder=f"thumbs/{task.id}"
                    ),
                    "image/jpeg",
                )

            db.add(
                Clip(
                    task_id=task.id,
                    clip_index=1,
                    start_time="00:00:00",
                    end_time=_fmt_hms(duration),
                    duration=duration,
                    title=f"Compose {len(local_paths)} klip",
                    download_url=download_url,
                    thumbnail_url=thumbnail_url,
                    file_size=Path(final_clip).stat().st_size,
                    editing_applied=[
                        k for k, v in options.items()
                        if v is not None and v is not False and v != ""
                    ]
                    + (["platform_watermark"] if brand_applied else []),
                )
            )

            task.total_clips = 1
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = _now()
            await db.commit()

            try:
                await CreditService.deduct_credits(
                    db, str(task.user_id), 1.0,
                    {"reason": "compose", "clips": 1}, task_id=str(task.id),
                )
                task.credits_spent = 1
                await db.commit()
            except Exception as exc:
                logger.warning("Gagal potong kredit compose %s: %s", task.id, exc)

            return {"ok": True, "clips": 1, "error": None}

        except Exception as exc:
            logger.exception("Compose gagal untuk task %s", task.id)
            task.status = TaskStatus.ERROR
            task.error_message = str(exc)[:2000]
            await db.commit()
            return {"ok": False, "clips": 0, "error": str(exc)}
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)



async def run_split_pipeline(task_id: UUID) -> Dict[str, Any]:
    """Potong satu klip jadi dua klip baru di detik `at_time`."""
    async with AsyncSessionLocal() as db:
        task: Optional[Task] = await db.get(Task, task_id)
        if task is None:
            return {"ok": False, "clips": 0, "error": "task not found"}

        options: Dict[str, Any] = task.editing_options or {}
        work_dir = Path(settings.WORKER_WORK_DIR) / str(task.id)
        work_dir.mkdir(parents=True, exist_ok=True)
        processor = VideoProcessor(str(work_dir))
        storage = get_storage()

        task.status = TaskStatus.PROCESSING
        task.progress = 10
        task.error_message = None
        await db.commit()

        try:
            clips = await _load_source_clips(db, task, [str(options.get("clip_id") or "")])
            source = clips[0]
            if not source.download_url:
                raise RuntimeError("The source clip has no download_url")

            at_time = float(options.get("at_time") or 0)
            if at_time <= 0:
                raise RuntimeError("at_time must be greater than 0")

            local = str(work_dir / f"source.{_ext_from_url(source.download_url)}")
            await _download_asset(source.download_url, local)
            await _set_progress(db, task, 40)

            info = await processor.get_video_info(local)
            total = float(info.get("duration") or 0)
            if at_time >= total - 0.3:
                raise RuntimeError(
                    f"at_time ({at_time:.2f}s) exceeds the clip duration ({total:.2f}s)"
                )

            out_a = str(work_dir / "part_a.mp4")
            out_b = str(work_dir / "part_b.mp4")
            await processor.split_clip(local, out_a, out_b, at_time)
            await _set_progress(db, task, 75)

            for index, path in enumerate((out_a, out_b), 1):
                part_info = await processor.get_video_info(path)
                part_duration = float(part_info.get("duration") or 0)
                url = storage.upload_file(
                    path,
                    storage.generate_object_key(
                        str(task.user_id), f"split_{index}.mp4", folder=f"clips/{task.id}"
                    ),
                    "video/mp4",
                )

                thumb_url = None
                thumb_path = await processor.extract_thumbnail(
                    path, str(work_dir / f"thumb_{index}.jpg")
                )
                if thumb_path:
                    thumb_url = storage.upload_file(
                        thumb_path,
                        storage.generate_object_key(
                            str(task.user_id), f"thumb_{index}.jpg", folder=f"thumbs/{task.id}"
                        ),
                        "image/jpeg",
                    )

                db.add(
                    Clip(
                        task_id=task.id,
                        clip_index=index,
                        start_time="00:00:00",
                        end_time=_fmt_hms(part_duration),
                        duration=part_duration,
                        title=f"{source.title} (bagian {index})",
                        download_url=url,
                        thumbnail_url=thumb_url,
                        file_size=Path(path).stat().st_size,
                        editing_applied=["split"],
                    )
                )

            task.total_clips = 2
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = _now()
            await db.commit()

            try:
                await CreditService.deduct_credits(
                    db, str(task.user_id), 2.0,
                    {"reason": "split", "clips": 2}, task_id=str(task.id),
                )
                task.credits_spent = 2
                await db.commit()
            except Exception as exc:
                logger.warning("Gagal potong kredit split %s: %s", task.id, exc)

            return {"ok": True, "clips": 2, "error": None}

        except Exception as exc:
            logger.exception("Split gagal untuk task %s", task.id)
            task.status = TaskStatus.ERROR
            task.error_message = str(exc)[:2000]
            await db.commit()
            return {"ok": False, "clips": 0, "error": str(exc)}
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

