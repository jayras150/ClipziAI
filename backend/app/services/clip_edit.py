"""Edit satu klip yang sudah dirender tanpa membuat Task baru (Batch E4)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.clip import Clip
from app.models.task import Task
from app.services.processor import VideoProcessor, get_caption_style
from app.services.storage_registry import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()

# Status in-memory per klip. Nilai akhir tetap disimpan di Clip.editing_applied
# dan viral_factors["manual_edit"] agar tidak hilang saat API restart.
EDIT_JOBS: Dict[str, Dict[str, Any]] = {}


async def _download(url: str, target: str) -> None:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        Path(target).write_bytes(response.content)


def _ffmpeg_color(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return "0x" + text[1:]
    return text or None


async def run_clip_edit(
    clip_id: UUID,
    user_id: UUID,
    options: Dict[str, Any],
) -> None:
    """Render edit klip di background lalu ganti URL klip secara atomik."""
    key = str(clip_id)
    EDIT_JOBS[key] = {"status": "processing", "progress": 5, "error": None}
    work_dir = Path(settings.WORKER_WORK_DIR) / "clip_edits" / key
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Clip)
                .join(Task, Clip.task_id == Task.id)
                .where(Clip.id == clip_id, Task.user_id == user_id)
            )
            clip = result.scalar_one_or_none()
            if clip is None:
                raise RuntimeError("Clip not found.")
            if not clip.download_url:
                raise RuntimeError("This clip has no video file to edit.")

            source = str(work_dir / "source.mp4")
            await _download(clip.download_url, source)
            EDIT_JOBS[key]["progress"] = 25

            processor = VideoProcessor(str(work_dir))
            info = await processor.get_video_info(source)
            if not info.get("has_audio"):
                ensured = str(work_dir / "source_audio.mp4")
                await processor.ensure_audio(source, ensured)
                source = ensured
                info = await processor.get_video_info(source)
            duration = float(info.get("duration") or clip.duration or 0)
            start = max(0.0, min(float(options.get("trim_start") or 0), max(0.0, duration - 0.2)))
            end_value = options.get("trim_end")
            end = float(end_value) if end_value not in (None, "") else duration
            end = max(start + 0.2, min(end, duration))
            speed = float(options.get("speed") or 1.0)
            filter_preset = options.get("filter_preset") or None

            trimmed = str(work_dir / "trimmed.mp4")
            await processor.trim_video(
                source,
                trimmed,
                start_time=start,
                end_time=end,
                speed=speed,
                filter_preset=str(filter_preset) if filter_preset else None,
            )
            final_clip = trimmed
            EDIT_JOBS[key]["progress"] = 60

            caption_text = str(options.get("caption_text") or "").strip()
            if caption_text:
                style_name = str(options.get("caption_style") or "classic")
                preset = get_caption_style(style_name)
                overlay = preset["overlay"]
                out_info = await processor.get_video_info(final_clip)
                out_h = int(out_info.get("height") or 1920)
                default_size = max(18, int(round(out_h * float(overlay["size_ratio"]))))
                try:
                    size = float(options.get("caption_size") or 0)
                except (TypeError, ValueError):
                    size = 0
                font_size = max(12, int(round(size))) if size > 0 else default_size
                captioned = str(work_dir / "captioned.mp4")
                await processor.add_text_overlay(
                    final_clip,
                    captioned,
                    caption_text,
                    font_size=font_size,
                    font_color=_ffmpeg_color(options.get("caption_color"))
                    or str(overlay["color"]),
                    x="(w-text_w)/2",
                    y=(
                        "h*0.07"
                        if str(overlay.get("y")) == "top"
                        else "(h-text_h)/2"
                        if str(overlay.get("y")) == "center"
                        else "h-text_h-h*0.085"
                    ),
                    box=bool(overlay.get("box", False)),
                    box_color=str(overlay.get("box_color") or "black@0.6"),
                    border_width=int(overlay.get("border_width") or 0),
                    border_color=str(overlay.get("border_color") or "black"),
                    font_name=str(options.get("caption_font") or "") or None,
                )
                final_clip = captioned
            EDIT_JOBS[key]["progress"] = 80

            storage = get_storage()
            object_key = storage.generate_object_key(
                str(user_id),
                "edited.mp4",
                folder=f"clips/{clip.task_id}",
            )
            download_url = storage.upload_file(final_clip, object_key, "video/mp4")
            if not download_url:
                raise RuntimeError("Storage did not return a URL for the edited clip.")

            final_info = await processor.get_video_info(final_clip)
            thumb_path = await processor.extract_thumbnail(
                final_clip, str(work_dir / "edited.jpg"), at_second=min(1.0, duration / 2)
            )
            thumbnail_url = clip.thumbnail_url
            if thumb_path:
                thumb_key = storage.generate_object_key(
                    str(user_id),
                    "edited.jpg",
                    folder=f"thumbs/{clip.task_id}",
                )
                thumbnail_url = storage.upload_file(thumb_path, thumb_key, "image/jpeg")

            factors = dict(clip.viral_factors or {})
            factors.setdefault("original_download_url", clip.download_url)
            factors["manual_edit"] = {
                "trim_start": round(start, 3),
                "trim_end": round(end, 3),
                "speed": speed,
                "filter_preset": filter_preset,
                "caption_text": caption_text,
                "caption_style": options.get("caption_style") or "classic",
                "caption_color": options.get("caption_color"),
                "caption_size": options.get("caption_size"),
                "caption_font": options.get("caption_font"),
            }
            clip.viral_factors = factors
            clip.download_url = download_url
            clip.thumbnail_url = thumbnail_url
            clip.duration = float(final_info.get("duration") or (end - start) / max(speed, 0.25))
            clip.file_size = Path(final_clip).stat().st_size
            applied = list(clip.editing_applied or [])
            for label in ("trim", "speed", "filter", "caption"):
                if label not in applied:
                    applied.append(label)
            clip.editing_applied = applied
            await db.commit()
            EDIT_JOBS[key] = {
                "status": "done",
                "progress": 100,
                "error": None,
                "download_url": download_url,
                "thumbnail_url": thumbnail_url,
            }
            logger.info("Edit klip %s selesai: %s", clip_id, download_url)
    except Exception as exc:
        logger.warning("Edit klip %s gagal: %s", clip_id, str(exc)[:400])
        EDIT_JOBS[key] = {
            "status": "error",
            "progress": 0,
            "error": str(exc)[:300],
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def edit_status(clip_id: UUID) -> Dict[str, Any]:
    return EDIT_JOBS.get(str(clip_id)) or {"status": "idle", "progress": 0, "error": None}
