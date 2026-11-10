"""
Watermark platform untuk plan tertentu (default: free).

Dipisah dari pipeline supaya `run_pipeline` (buat klip) dan `run_compose_pipeline`
(merge/split) memakai aturan yang sama — kalau tidak, user free bisa menghilangkan
watermark dengan cara merge klip.

Sumber konfigurasi: tabel `platform_settings` key `watermark` (diatur admin).
"""
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.task import Task
from app.models.user_profile import UserProfile
from app.services.platform_settings import get_watermark_config, plan_is_watermarked
from app.services.processor import VideoProcessor

logger = logging.getLogger(__name__)


async def _resolve_plan(db, task: Task) -> str:
    """Plan yang dipakai saat task dibuat; fallback ke profil user, lalu 'free'."""
    plan = getattr(task, "plan_at_time", None)
    if plan:
        return str(plan).lower()
    try:
        result = await db.execute(
            select(UserProfile.plan_type).where(UserProfile.user_id == task.user_id)
        )
        value = result.scalar_one_or_none()
        if value is not None:
            return str(getattr(value, "value", value)).lower()
    except Exception as exc:  # pragma: no cover - jangan gagalkan render
        logger.warning("Gagal membaca plan user %s: %s", task.user_id, exc)
    return "free"


def _position_xy(position: str, margin: int) -> Tuple[str, str]:
    """Ekspresi drawtext (x, y) untuk posisi yang didukung admin."""
    m = max(0, int(margin))
    return {
        "top-left": (f"{m}", f"{m}"),
        "top-right": (f"w-text_w-{m}", f"{m}"),
        "bottom-left": (f"{m}", f"h-text_h-{m}"),
        "bottom-right": (f"w-text_w-{m}", f"h-text_h-{m}"),
        "center": ("(w-text_w)/2", "(h-text_h)/2"),
    }.get(position, (f"w-text_w-{m}", f"h-text_h-{m}"))


async def _download(url: str, dest: str) -> str:
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        Path(dest).write_bytes(response.content)
    return dest


async def apply_platform_watermark(
    processor: VideoProcessor,
    task: Task,
    input_path: str,
    output_path: str,
    work_dir: str | Path,
) -> Tuple[str, bool]:
    """
    Tempel watermark platform bila plan user termasuk sasaran.

    Return `(path, applied)`. Semua kegagalan dikembalikan sebagai "tidak
    diterapkan" + warning, karena watermark tidak boleh menggagalkan render
    (klip tetap berguna; admin bisa cek log).
    """
    try:
        async with AsyncSessionLocal() as db:
            config: Dict[str, Any] = await get_watermark_config(db)
            if not config.get("enabled"):
                return input_path, False
            plan = await _resolve_plan(db, task)
            if not plan_is_watermarked(plan, config):
                return input_path, False
    except Exception as exc:
        logger.warning("Setelan watermark tidak terbaca untuk task %s: %s", task.id, exc)
        return input_path, False

    try:
        image_url = config.get("image_url")
        if image_url:
            suffix = "png" if str(image_url).lower().split("?")[0].endswith(".png") else "img"
            dest = str(Path(work_dir) / f"brand_{uuid4().hex}.{suffix}")
            await _download(str(image_url), dest)
            await processor.overlay_image(
                input_path,
                dest,
                output_path,
                position=str(config.get("position") or "bottom-right"),
                scale=float(config.get("scale") or 0.18),
                opacity=float(config.get("opacity") or 0.85),
                margin=int(config.get("margin") or 24),
            )
            return output_path, True

        text = config.get("text")
        if text:
            info = await processor.get_video_info(input_path)
            height = int(info.get("height") or 1920)
            font_size = max(18, int(height * 0.028))
            color = str(config.get("text_color") or "#ffffff").replace("#", "0x")
            x, y = _position_xy(str(config.get("position") or "bottom-right"), int(config.get("margin") or 40))
            await processor.add_text_overlay(
                input_path,
                output_path,
                str(text),
                font_size=font_size,
                font_color=f"{color}@{float(config.get('opacity') or 0.85):.2f}",
                x=x,
                y=y,
                box=False,
                border_width=2,
                border_color="black@0.45",
            )
            return output_path, True
    except Exception as exc:
        logger.warning("Watermark platform gagal untuk task %s: %s", task.id, exc)

    return input_path, False


__all__ = ["apply_platform_watermark"]
