"""
Pipeline pemrosesan video — dipakai worker serverless Vast.ai dan mode inline.

Alur:
  download (yt-dlp + cookie pool) → probe ffprobe → ekstrak audio →
  transkripsi (API provider) → deteksi scene → potong + crop 9:16 →
  burn subtitle → upload ke Cloudflare R2 → simpan baris Clip.

Semua state berada di luar proses (PostgreSQL, Redis, R2), sehingga fungsi ini
aman dijalankan di worker mana pun, bahkan beberapa worker paralel sekaligus.
"""
import asyncio
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.clip import Clip
from app.models.task import Task, TaskStatus
from app.services import cookie_store
from app.services.clip_planner import plan_clip_quota, plan_clips
from app.services.credit_service import CreditService
from app.services.downloader import VideoDownloader
from app.services.local_llm import get_local_llm
from app.services.processor import VideoProcessor, get_caption_style
from app.services.speech_boundaries import detect_silences
from app.services.storage import R2Storage
from app.services.transcriber import AudioTranscriber
from app.services.viral import score_clip
from app.services.platform_watermark import apply_platform_watermark

logger = logging.getLogger(__name__)

settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_hms(seconds: float) -> str:
    """Detik -> 'HH:MM:SS' (format kolom Clip.start_time/end_time)."""
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


async def _download_asset(url: str, dest: str) -> str:
    """Unduh aset pendukung (logo/intro/outro/musik) ke folder kerja."""
    import httpx

    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        Path(dest).write_bytes(response.content)
    return dest


def _ext_from_url(url: str, default: str = "mp4") -> str:
    """Ambil ekstensi file dari URL (untuk penamaan aset sementara)."""
    path = str(url).split("?")[0].rstrip("/")
    tail = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return tail if tail and len(tail) <= 5 and tail.isalnum() else default


async def _set_progress(db, task: Task, percent: int, stage: str | None = None) -> None:
    task.progress = max(0, min(100, int(percent)))
    await db.commit()
    try:
        from app.services.worker_callback import report_worker_event

        await report_worker_event(task.id, "stage", stage=stage, progress=task.progress)
    except Exception:
        pass


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

        # ---- Editing lanjutan atas klip yang sudah jadi ----
        # "compose" (gabung beberapa klip) dan "split" (potong klip) tidak perlu
        # mengunduh video sumber, jadi ditangani modul terpisah.
        mode = str((task.editing_options or {}).get("mode") or "").strip().lower()
        if mode in {"compose", "split"}:
            from app.services.pipeline_compose import (
                run_compose_pipeline,
                run_split_pipeline,
            )

            await db.close()
            if mode == "compose":
                return await run_compose_pipeline(task_id)
            return await run_split_pipeline(task_id)

        task.status = TaskStatus.PROCESSING
        task.progress = 1
        task.error_message = None
        await db.commit()

        work_dir = Path(settings.WORKER_WORK_DIR) / str(task.id)
        work_dir.mkdir(parents=True, exist_ok=True)

        # Log proses worker → /tmp/clipzi-worker.log (diunggah ke qurl.sh di akhir).
        try:
            from app.services.log_bundle import install_file_logger

            install_file_logger()
        except Exception:
            pass

        downloader = VideoDownloader(str(work_dir / "input"))
        processor = VideoProcessor(str(work_dir))
        transcriber = AudioTranscriber()
        storage = R2Storage()

        options: Dict[str, Any] = task.editing_options or {}
        # ---- observability: catat durasi tiap stage (B11) ----
        stage_marks: Dict[str, float] = {}
        _stage_start = time.perf_counter()

        def _lap(stage: str) -> None:
            stage_marks[stage] = round(time.perf_counter() - _stage_start, 2)

        burn_subtitle = bool(options.get("burn_subtitle", True))
        # Panjang klip: TIDAK dipaksa bulat. Ini hanya jendela target; batas
        # akhir mengikuti akhir kalimat (bisa 1:03, 1:16, dst).
        min_duration = float(
            options.get("target_duration_min") or task.target_duration_min or 60
        )
        max_duration = float(
            options.get("target_duration_max") or task.target_duration_max or 90
        )
        if max_duration < min_duration:
            min_duration, max_duration = max_duration, min_duration
        min_duration = max(60.0, min_duration)
        requested_clips = options.get("max_clips")
        max_clips = int(requested_clips) if requested_clips else 0  # 0 = auto
        # ---------- Fase 1: editing manual ----------
        manual_start = options.get("start_time")
        manual_end = options.get("end_time")
        aspect_ratio = str(options.get("aspect_ratio", "9:16"))
        caption_text = options.get("caption_text")
        # Gaya caption: preset di app/services/processor.py (CAPTION_STYLES).
        caption_style = str(options.get("caption_style") or "").strip().lower()
        speed = float(options.get("speed", 1.0) or 1.0)
        # ---------- Fase 2: gaya & polish ----------
        filter_preset = options.get("filter_preset")
        blur_fill = bool(options.get("blur_fill", False))
        trim_silence = bool(options.get("remove_silence", False))
        clean_audio = bool(options.get("enhance_audio", False))
        watermark_url = options.get("watermark_url")
        watermark_position = str(options.get("watermark_position", "bottom-right"))
        watermark_opacity = float(options.get("watermark_opacity", 0.85) or 0.85)
        watermark_scale = float(options.get("watermark_scale", 0.16) or 0.16)
        intro_url = options.get("intro_url")
        outro_url = options.get("outro_url")
        # ---------- Auto zoom follow-speaker ----------
        auto_zoom = str(options.get("auto_zoom") or "").strip().lower()
        zoom_level = float(options.get("zoom_level", 1.0) or 1.0)
        # ---------- Musik latar ----------
        music_url = options.get("music_url")
        music_volume = float(options.get("music_volume", 0.22) or 0.22)
        music_ducking = bool(options.get("music_ducking", True))

        local_llm = None
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
            _lap("downloaded")

            # 3) Ekstrak audio + transkripsi (API provider)
            segments: List[Dict[str, Any]] = []
            raw_segments: List[Dict[str, Any]] = []
            transcription_backend = "unknown"
            try:
                audio_path = await processor.extract_audio(
                    video_path, str(work_dir / "audio.mp3")
                )
                result = await transcriber.transcribe(audio_path)
                segments = list(result.get("segments") or [])
                # Segmen mentah menyimpan timestamp kata — dipakai planner untuk
                # memotong tepat di jeda kalimat.
                raw_segments = list(result.get("raw_segments") or segments)
                transcription_backend = str(result.get("backend") or "unknown")
                logger.info(
                    "Pipeline: %s segmen transkripsi (%s mentah, backend=%s) untuk task %s",
                    len(segments),
                    len(raw_segments),
                    transcription_backend,
                    task.id,
                )
            except Exception as exc:
                # Transkripsi gagal bukan alasan menggagalkan task; klip tetap
                # dibuat, hanya tanpa subtitle.
                logger.warning("Transkripsi gagal untuk task %s: %s", task.id, exc)
            await _set_progress(db, task, 35)
            _lap("transcribed")

            # Whisper dilepas lebih dulu supaya VRAM cukup untuk LLM lokal.
            try:
                transcriber.unload_model()
            except Exception as exc:
                logger.warning("Gagal melepas model Whisper dari VRAM: %s", exc)

            # LLM lokal (Qwen3-4B-Instruct-2507 via llama.cpp) untuk rerank momen
            # viral + metadata. Kalau gagal start, planner tetap jalan heuristik.
            local_llm = get_local_llm()
            llm_ready = False
            if settings.LOCAL_LLM_ENABLED:
                llm_ready = await asyncio.get_event_loop().run_in_executor(
                    None, local_llm.start
                )
                if not llm_ready:
                    logger.warning(
                        "LLM lokal tidak siap — planner memakai skor heuristik saja"
                    )
                    try:
                        from app.services.worker_callback import report_worker_event

                        await report_worker_event(
                            task.id,
                            "stage",
                            stage="llm_failed",
                            message=local_llm._tail_log()[:400],
                        )
                    except Exception:
                        pass
                _lap("llm_ready")
                if llm_ready:
                    try:
                        from app.services.worker_callback import report_worker_event

                        await report_worker_event(
                            task.id,
                            "stage",
                            stage="llm_info",
                            message=str(getattr(local_llm, "info", ""))[:400],
                        )
                    except Exception:
                        pass

            # 4) Tentukan rentang klip — manual trim prioritas atas planner
            total_duration = float(info.get("duration") or 0)
            if total_duration and total_duration < 60:
                raise RuntimeError(
                    "Source video must be at least 1 minute long — clips need enough "
                    "conversation to cut at natural sentence boundaries."
                )
            if max_clips <= 0:
                max_clips = plan_clip_quota(total_duration)
            # Kapasitas fisik: tidak mungkin lebih banyak klip daripada durasi
            # sumber dibagi panjang minimum klip.
            capacity = max(1, int(total_duration // max(20.0, min_duration * 0.92)))
            max_clips = max(1, min(max_clips, capacity, 10))
            task.total_clips = max_clips
            await db.commit()

            planned: List[Dict[str, Any]] = []
            planned_by_start: Dict[float, Dict[str, Any]] = {}

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
                # Planner berbasis ucapan: pilih kalimat utuh, sebar merata.
                try:
                    silences = await asyncio.get_event_loop().run_in_executor(
                        None, detect_silences, video_path
                    )
                    planned = plan_clips(
                        raw_segments,
                        silences,
                        total_duration,
                        min_duration,
                        max_duration,
                        max_clips,
                        llm=local_llm if llm_ready else None,
                    )
                except Exception as exc:
                    logger.warning(
                        "Clip planner gagal untuk task %s: %s", task.id, exc
                    )
                    planned = []

                if planned:
                    planned_by_start = {
                        round(float(item["start"]), 2): item for item in planned
                    }
                    ranges = [
                        (round(float(item["start"]), 2), round(float(item["duration"]), 2))
                        for item in planned
                    ]
                    logger.info(
                        "Pipeline: planner memilih %s klip untuk task %s: %s",
                        len(ranges),
                        task.id,
                        [f"{s:.1f}-{s + d:.1f}" for s, d in ranges],
                    )
                    rerank_applied = any(
                        (item.get("factors") or {}).get("reranked_by") for item in planned
                    )
                    rerank_error = "" if rerank_applied else str(
                        getattr(local_llm, "last_error", "")
                    )[:300]
                    for item in planned:
                        factors = item.setdefault("factors", {})
                        factors["rerank_applied"] = rerank_applied
                        if rerank_error:
                            factors["rerank_error"] = rerank_error
                    if llm_ready and not rerank_applied:
                        # LLM hidup tapi rerank tidak terpakai — kirim alasannya ke
                        # admin (worker log tidak bisa dibaca dari VPS).
                        try:
                            from app.services.worker_callback import report_worker_event

                            await report_worker_event(
                                task.id,
                                "stage",
                                stage="rerank_skipped",
                                message=rerank_error,
                            )
                        except Exception:
                            pass
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

            # ---------- Metadata AI lokal (judul/deskripsi/tag) ----------
            # Dibuat SEBELUM render supaya LLM bisa dimatikan dan VRAM-nya dipakai
            # ffmpeg. Hasil disimpan ke Clip.ai_suggested_* saat menyimpan klip.
            clip_metadata: Dict[float, Dict[str, Any]] = {}
            if llm_ready and ranges and segments:
                try:
                    from app.services.ai_client import make_ai_client
                    from app.services.metadata_generator import MetadataGenerator

                    generator = MetadataGenerator(
                        client=make_ai_client(local_llm.base_url),
                        model=local_llm.model_name,
                    )
                    for meta_start, meta_duration in ranges:
                        transcript_text = " ".join(
                            str(seg.get("text") or "").strip()
                            for seg in _slice_segments(
                                segments, meta_start, meta_start + meta_duration
                            )
                        ).strip()
                        if len(transcript_text.split()) < 6:
                            continue
                        try:
                            clip_metadata[round(meta_start, 2)] = await generator.generate(
                                transcript=transcript_text,
                                source_title="",
                                duration=float(meta_duration),
                                start_time=_fmt_hms(meta_start),
                                end_time=_fmt_hms(meta_start + meta_duration),
                            )
                        except Exception as exc:
                            logger.warning(
                                "Metadata AI lokal gagal (task %s klip %.1fs): %s",
                                task.id,
                                meta_start,
                                str(exc)[:200],
                            )
                except Exception as exc:
                    logger.warning(
                        "Metadata AI lokal dilewati untuk task %s: %s", task.id, exc
                    )
            _lap("metadata")

            # Kecepatan decode Qwen (bukti GPU vs CPU) — dikirim sebelum LLM mati.
            if llm_ready:
                try:
                    from app.services.worker_callback import report_worker_event

                    await report_worker_event(
                        task.id,
                        "stage",
                        stage="llm_perf",
                        message=local_llm.runtime_info(),
                    )
                except Exception:
                    pass

            # VRAM harus bebas sebelum render ffmpeg.
            if llm_ready:
                try:
                    local_llm.stop()
                except Exception:
                    pass


            # 5) Render tiap klip
            rendered: List[Dict[str, Any]] = []
            total = len(ranges)
            for index, (start, duration) in enumerate(ranges, 1):
                raw_clip = str(work_dir / f"clip_{index:02d}_raw.mp4")
                if auto_zoom in {"speaker", "face", "follow"}:
                    # Auto zoom: jendela crop mengikuti wajah pembicara.
                    await processor.track_speaker_crop(
                        video_path,
                        raw_clip,
                        start_time=start,
                        duration=duration,
                        aspect_ratio=aspect_ratio,
                        zoom=zoom_level,
                        filter_preset=filter_preset,
                    )
                else:
                    await processor.render_clip(
                        video_path,
                        raw_clip,
                        start_time=start,
                        duration=duration,
                        aspect_ratio=aspect_ratio,
                        filter_preset=filter_preset,
                        blur_fill=blur_fill,
                    )

                final_clip = raw_clip
                subtitle_url: Optional[str] = None

                # Buang jeda/senyap (jump cuts) sebelum efek berikutnya.
                if trim_silence:
                    silenced = str(work_dir / f"clip_{index:02d}_silence.mp4")
                    try:
                        await processor.remove_silence(final_clip, silenced)
                        final_clip = silenced
                    except Exception as exc:
                        logger.warning(
                            "Remove silence gagal (task %s klip %s): %s", task.id, index, exc
                        )
                if burn_subtitle and segments:
                    sliced = _slice_segments(segments, start, start + duration)
                    if sliced:
                        srt_path = str(work_dir / f"clip_{index:02d}.srt")
                        transcriber.generate_srt(sliced, srt_path)

                        # Utamakan ASS (karaoke per kata, 2 baris, posisi aman).
                        # SRT tetap dibuat untuk tombol unduh subtitle.
                        burn_path = srt_path
                        try:
                            from app.services.caption_ass import build_ass

                            preset = get_caption_style(caption_style)
                            out_w, out_h = processor._dimensions_for_ratio(aspect_ratio)
                            ass_path = str(work_dir / f"clip_{index:02d}.ass")
                            built = build_ass(
                                raw_segments or segments,
                                ass_path,
                                str(preset.get("force_style") or ""),
                                out_w,
                                out_h,
                                clip_start=start,
                                clip_end=start + duration,
                            )
                            if built:
                                burn_path = built
                        except Exception as exc:
                            logger.warning(
                                "Caption ASS gagal (task %s klip %s): %s — pakai SRT",
                                task.id,
                                index,
                                exc,
                            )

                        # Burn subtitle bersifat opsional: kalau ffmpeg gagal
                        # (font/filter/path), klip tetap dikirim tanpa subtitle
                        # alih-alih menggagalkan seluruh task.
                        burned = str(work_dir / f"clip_{index:02d}_sub.mp4")
                        try:
                            await processor.burn_subtitle(
                                raw_clip, burn_path, burned, style=caption_style
                            )
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
                        # Ukuran font mengikuti tinggi output supaya caption
                        # tetap terbaca di 9:16, 1:1, dan 16:9.
                        caption_preset = get_caption_style(caption_style)
                        overlay = caption_preset["overlay"]
                        _, out_h = processor._dimensions_for_ratio(aspect_ratio)
                        font_size = max(18, int(round(out_h * float(overlay["size_ratio"]))))
                        vertical = str(overlay.get("y") or "bottom")
                        if vertical == "top":
                            y_expr = "h*0.07"
                        elif vertical == "center":
                            y_expr = "(h-text_h)/2"
                        else:
                            y_expr = "h-text_h-h*0.085"
                        await processor.add_text_overlay(
                            final_clip,
                            captioned,
                            caption_text,
                            font_size=font_size,
                            font_color=str(overlay["color"]),
                            x="(w-text_w)/2",
                            y=y_expr,
                            box=bool(overlay.get("box", False)),
                            box_color=str(overlay.get("box_color") or "black@0.6"),
                            border_width=int(overlay.get("border_width") or 0),
                            border_color=str(overlay.get("border_color") or "black"),
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

                # ---------- Musik latar (ducking di bawah narasi) ----------
                if music_url:
                    try:
                        music_path = str(
                            work_dir / f"music.{_ext_from_url(str(music_url), 'mp3')}"
                        )
                        await _download_asset(str(music_url), music_path)
                        mixed = str(work_dir / f"clip_{index:02d}_music.mp4")
                        await processor.mix_music(
                            final_clip,
                            music_path,
                            mixed,
                            volume=music_volume,
                            ducking=music_ducking,
                        )
                        final_clip = mixed
                    except Exception as exc:
                        logger.warning(
                            "Mix musik gagal (task %s klip %s): %s", task.id, index, exc
                        )

                # ---------- Watermark / logo ----------
                if watermark_url:
                    try:
                        wm_path = str(work_dir / f"clip_{index:02d}_wm.{_ext_from_url(watermark_url, 'png')}")
                        await _download_asset(str(watermark_url), wm_path)
                        stamped = str(work_dir / f"clip_{index:02d}_wm.mp4")
                        await processor.overlay_image(
                            final_clip,
                            wm_path,
                            stamped,
                            position=watermark_position,
                            scale=watermark_scale,
                            opacity=watermark_opacity,
                        )
                        final_clip = stamped
                    except Exception as exc:
                        logger.warning(
                            "Watermark gagal (task %s klip %s): %s", task.id, index, exc
                        )

                # ---------- Watermark platform (wajib untuk plan tertentu) ----------
                # Diterapkan SETELAH watermark user supaya logo Clipzy selalu di atas
                # dan tidak bisa dihilangkan dengan mengunggah logo sendiri.
                brand_applied = False
                try:
                    branded = str(work_dir / f"clip_{index:02d}_brand.mp4")
                    brand_source, brand_applied = await apply_platform_watermark(
                        processor, task, final_clip, branded, work_dir
                    )
                    if brand_applied:
                        final_clip = brand_source
                except Exception as exc:
                    logger.warning(
                        "Watermark platform gagal (task %s klip %s): %s", task.id, index, exc
                    )

                # ---------- Perbaikan audio (denoise + loudnorm) ----------
                if clean_audio:
                    try:
                        clean_path = str(work_dir / f"clip_{index:02d}_audio.mp4")
                        await processor.enhance_audio(final_clip, clean_path)
                        final_clip = clean_path
                    except Exception as exc:
                        logger.warning(
                            "Enhance audio gagal (task %s klip %s): %s", task.id, index, exc
                        )

                # ---------- Intro / outro ----------
                if intro_url or outro_url:
                    try:
                        pieces: List[str] = []
                        if intro_url:
                            intro_path = str(
                                work_dir / f"intro_{index:02d}.{_ext_from_url(intro_url)}"
                            )
                            await _download_asset(str(intro_url), intro_path)
                            pieces.append(intro_path)
                        pieces.append(final_clip)
                        if outro_url:
                            outro_path = str(
                                work_dir / f"outro_{index:02d}.{_ext_from_url(outro_url)}"
                            )
                            await _download_asset(str(outro_url), outro_path)
                            pieces.append(outro_path)

                        joined = str(work_dir / f"clip_{index:02d}_joined.mp4")
                        out_w, out_h = processor._dimensions_for_ratio(aspect_ratio)
                        await processor.concat_videos(pieces, joined, width=out_w, height=out_h)
                        final_clip = joined
                    except Exception as exc:
                        logger.warning(
                            "Intro/outro gagal (task %s klip %s): %s", task.id, index, exc
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

                # Skor viral: pakai hasil planner (hook, payoff, kohesi, batas
                # kalimat) bila ada; kalau tidak, hitung ulang dari transkrip klip.
                plan = planned_by_start.get(round(start, 2))
                if plan is not None:
                    viral = {"score": plan["score"], "factors": dict(plan["factors"])}
                    viral["factors"]["planned"] = True
                    viral["factors"]["transcript"] = str(plan.get("transcript") or "")[:2000]
                    viral["factors"]["transcript_words"] = len(
                        str(plan.get("transcript") or "").split()
                    )
                else:
                    clip_transcript = " ".join(
                        str(seg.get("text") or "").strip()
                        for seg in _slice_segments(segments or [], start, start + duration)
                    ).strip()
                    viral = score_clip(
                        transcript=clip_transcript,
                        duration=duration,
                        has_subtitle=bool(subtitle_url),
                        has_caption=bool(caption_text),
                    )
                    # Simpan transkrip di JSONB viral_factors (tanpa kolom baru) supaya
                    # skor bisa dihitung ulang penuh & siap dipakai karaoke caption.
                    if clip_transcript:
                        viral["factors"]["transcript"] = clip_transcript[:2000]
                        viral["factors"]["transcript_words"] = len(clip_transcript.split())


                rendered.append(
                    {
                        "start": start,
                        "duration": duration,
                        "download_url": download_url,
                        "subtitle_url": subtitle_url,
                        "thumbnail_url": thumbnail_url,
                        "file_size": Path(final_clip).stat().st_size,
                        "viral": viral,
                        "brand": brand_applied,
                        "meta": clip_metadata.get(round(start, 2)),
                    }
                )
                await _set_progress(db, task, 35 + int(55 * index / max(1, total)))

            # 6) Simpan klip & tandai task selesai
            _lap("rendered")
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
                        viral_score=(clip.get("viral") or {}).get("score"),
                        viral_factors=(clip.get("viral") or {}).get("factors"),
                        ai_suggested_title=((clip.get("meta") or {}).get("title") or None),
                        ai_suggested_description=(
                            (clip.get("meta") or {}).get("description") or None
                        ),
                        ai_suggested_tags=((clip.get("meta") or {}).get("tags") or None),
                        editing_applied=[
                            k
                            for k, v in options.items()
                            if v is not None and v is not False and v != ""
                        ]
                        + (["platform_watermark"] if clip.get("brand") else []),
                    )
                )

            task.total_clips = len(rendered)
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.completed_at = _now()
            await db.commit()
            _lap("saved")

            # Ringkasan durasi per stage — dipakai untuk analisa worker lambat.
            def _delta(a: str, b: str) -> float:
                return round(max(0.0, stage_marks.get(b, 0.0) - stage_marks.get(a, 0.0)), 2)

            logger.info(
                "Timing task %s: unduh=%.2fs transkripsi=%.2fs (%s) render=%.2fs simpan=%.2fs total=%.2fs",
                task.id,
                stage_marks.get("downloaded", 0.0),
                _delta("downloaded", "transcribed"),
                transcription_backend,
                _delta("transcribed", "rendered"),
                _delta("rendered", "saved"),
                stage_marks.get("saved", 0.0),
            )

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
            try:
                from app.services.worker_callback import report_worker_event

                await report_worker_event(task.id, "done", progress=100)
            except Exception:
                pass
            return {"ok": True, "clips": len(rendered), "error": None}

        except Exception as exc:
            logger.exception("Pipeline gagal untuk task %s", task.id)
            task.status = TaskStatus.ERROR
            task.error_message = str(exc)[:2000]
            await db.commit()
            try:
                from app.services.worker_callback import report_worker_event

                await report_worker_event(task.id, "error", message=str(exc)[:400])
            except Exception:
                pass
            return {"ok": False, "clips": 0, "error": str(exc)}

        finally:
            try:
                if local_llm is not None:
                    local_llm.stop()
            except Exception:
                pass
            # Unggah log ke qurl.sh SEKALI, lalu laporkan hasilnya. Kegagalan di
            # sini tidak boleh menggagalkan task maupun mengirim callback ganda.
            log_reported = False
            try:
                from app.services.log_bundle import upload_log_bundle
                from app.services.worker_callback import report_worker_event

                log_url, log_error = await upload_log_bundle(str(task.id), str(work_dir))
                if log_url:
                    await report_worker_event(
                        task.id, "stage", stage="logs", message=log_url
                    )
                else:
                    await report_worker_event(
                        task.id, "stage", stage="logs_failed", message=log_error[:400]
                    )
                log_reported = True
            except Exception as exc:
                # traceback lengkap masuk worker.log (ikut terkirim bila memungkinkan)
                logger.exception("Unggah/lapor log worker gagal: %s", exc)
                if not log_reported:
                    try:
                        from app.services.worker_callback import report_worker_event

                        await report_worker_event(
                            task.id,
                            "stage",
                            stage="logs_failed",
                            message=f"{type(exc).__name__}: {exc}"[:400],
                        )
                    except Exception:
                        logger.exception("Gagal mengirim logs_failed ke API")
            shutil.rmtree(work_dir, ignore_errors=True)


