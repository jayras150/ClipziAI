"""
Clip endpoints - detail satu klip + metadata YouTube yang dibuat AI.

Metadata (judul, deskripsi, tag) selalu dibuat dari **transkrip klip** hasil
Whisper. Klip lama yang belum punya transkrip ditranskripsi ulang otomatis saat
metadata diminta, sehingga AI tidak pernah mengarang isi video.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from typing import Optional, Tuple
from uuid import UUID

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.ai_regenerate import AiRegenerateLog
from app.models.clip import Clip
from app.models.task import Task
from app.models.user import User
from app.schemas.clip import (
    ClipDetailResponse,
    ClipMetadataRequest,
    ClipMetadataResponse,
    ClipMetadataUpdate,
)
from app.services.metadata_generator import (
    MIN_TRANSCRIPT_WORDS,
    MetadataGenerationError,
    MetadataGenerator,
    _clean_tags,
)
from app.services.transcriber import AudioTranscriber

logger = logging.getLogger(__name__)

router = APIRouter()


def _stored_transcript(clip: Clip) -> str:
    """Transkrip klip yang disimpan pipeline di `viral_factors.transcript`."""
    factors = clip.viral_factors if isinstance(clip.viral_factors, dict) else {}
    return str(factors.get("transcript") or "").strip()


async def _load_clip(db: AsyncSession, clip_id: str, user_id: UUID) -> Tuple[Clip, Task]:
    """Ambil klip milik user (lewat task) atau 404."""
    try:
        cid = UUID(clip_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid clip id.")

    result = await db.execute(
        select(Clip, Task)
        .join(Task, Clip.task_id == Task.id)
        .where(Clip.id == cid, Task.user_id == user_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Clip not found.")
    clip, task = row
    return clip, task


def _download_clip(url: str, target: str) -> None:
    """Unduh berkas klip dari R2 ke disk (dipakai untuk transkripsi ulang)."""
    with requests.get(url, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(target, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    handle.write(chunk)


async def _transcribe_clip_url(url: str) -> str:
    """Transkripsi audio dari URL klip memakai layanan Whisper yang dikonfigurasi."""
    with tempfile.TemporaryDirectory() as work_dir:
        path = os.path.join(work_dir, "clip.mp4")
        await asyncio.to_thread(_download_clip, url, path)
        result = await AudioTranscriber().transcribe(path)
        text = str(result.get("full_text") or "").strip()
        if not text:
            pieces = [
                str(seg.get("text") or "").strip()
                for seg in (result.get("segments") or [])
            ]
            text = " ".join(piece for piece in pieces if piece).strip()
        return text


_SRT_TIME = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?[,.]\d{1,3}\s*-->")
_TAG = re.compile(r"<[^>]+>")


def _parse_subtitle(text: str) -> str:
    """Ambil teks dari file SRT/VTT (buang nomor urut, timestamp, dan tag HTML)."""
    pieces: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.isdigit() or _SRT_TIME.match(line):
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        clean = _TAG.sub("", line).strip()
        if clean:
            pieces.append(clean)
    # Buang pengulangan kata yang sering muncul di caption karaoke.
    deduped: list[str] = []
    for piece in pieces:
        if not deduped or deduped[-1] != piece:
            deduped.append(piece)
    return " ".join(deduped).strip()


def _subtitle_text(url: str) -> str:
    """Unduh subtitle klip (SRT/VTT) dari R2 lalu ambil teksnya."""
    with requests.get(url, timeout=90) as response:
        response.raise_for_status()
        return _parse_subtitle(response.text)


_BILLING_WORDS = ("402", "credit", "kredit", "quota", "kuota", "billing", "payment")


def _friendly_transcription_error(message: str) -> str:
    """Ubah error teknis transkripsi menjadi pesan yang bisa ditindaklanjuti."""
    low = (message or "").lower()
    if "local whisper" in low or "fallback lokal juga gagal" in low or "whisper lokal" in low:
        return (
            "Could not create the clip transcript: the Whisper provider refused the request (out of credit) "
            "and the local Whisper model could not load. Try again shortly, or reprocess the video so a transcript is stored."
        )
    if any(word in low for word in _BILLING_WORDS):
        return (
            "The Whisper transcription credit is exhausted. No metadata was generated to avoid inventing content; "
            "top up the credit or reprocess the video."
        )
    return (message or "Transcription failed.")[:260]



async def _store_transcript(clip: Clip, db: AsyncSession, text: str, source: str) -> None:
    """Simpan transkrip ringkas di JSONB `viral_factors` (tanpa kolom baru)."""
    factors = dict(clip.viral_factors or {})
    factors["transcript"] = text[:2000]
    factors["transcript_words"] = len(text.split())
    factors["transcript_source"] = source
    clip.viral_factors = factors
    await db.commit()


async def _ensure_transcript(clip: Clip, db: AsyncSession) -> Tuple[str, str]:
    """
    Pastikan ada transkrip untuk klip ini.

    Urutan sumber:
      1. `viral_factors.transcript` — hasil Whisper saat pipeline render.
      2. File subtitle (SRT/VTT) klip — teks asli ucapan, cepat, tanpa biaya.
      3. Transkripsi ulang klip dengan Whisper (bisa lambat / butuh kredit).

    Return `(transcript, source)`.
    """
    text = _stored_transcript(clip)
    if len(text.split()) >= MIN_TRANSCRIPT_WORDS:
        return text, "stored"

    if clip.subtitle_url:
        try:
            subtitle = await asyncio.to_thread(_subtitle_text, clip.subtitle_url)
        except Exception as exc:
            logger.warning("Gagal membaca subtitle klip %s: %s", clip.id, str(exc)[:200])
            subtitle = ""
        if len(subtitle.split()) >= MIN_TRANSCRIPT_WORDS:
            await _store_transcript(clip, db, subtitle, "subtitle")
            return subtitle, "subtitle"

    if not clip.download_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This clip has no video file, so a transcript cannot be created.",
        )

    try:
        text = await _transcribe_clip_url(clip.download_url)
    except Exception as exc:  # provider Whisper error, jaringan, dsb.
        logger.warning("Transkripsi ulang klip %s gagal: %s", clip.id, str(exc)[:300])
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_friendly_transcription_error(f"Could not create the clip transcript: {str(exc)[:300]}"),
        )

    words = text.split()
    if len(words) < MIN_TRANSCRIPT_WORDS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This clip has too little speech to ground the metadata, so nothing was generated."
            ),
        )

    await _store_transcript(clip, db, text, "on_demand_whisper")
    return text, "whisper"


def _hook_of(clip: Clip) -> Optional[str]:
    factors = clip.viral_factors if isinstance(clip.viral_factors, dict) else {}
    hook = factors.get("ai_hook")
    return str(hook) if hook else None


# Klip lama tanpa transkrip diproses di latar belakang (transkripsi bisa >100 detik,
# lebih lama dari batas timeout Cloudflare), jadi statusnya dilacak di sini.
_PREPARING: set[UUID] = set()
# Pesan kegagalan terakhir per klip supaya UI tidak menunggu selamanya.
_PREPARE_ERROR: dict[UUID, str] = {}


async def _prepare_metadata_bg(clip_id: UUID, user_id: UUID) -> None:
    """Transkripsi ulang klip lama lalu buat metadata AI (tanpa menahan request)."""
    try:
        async with AsyncSessionLocal() as db:
            clip, _task = await _load_clip(db, str(clip_id), user_id)
            transcript, _source = await _ensure_transcript(clip, db)
            result = await MetadataGenerator().generate(
                transcript=transcript,
                source_title=clip.title or "",
                duration=float(clip.duration or 0),
                start_time=clip.start_time or "",
                end_time=clip.end_time or "",
            )
            clip.ai_suggested_title = result["title"][:500]
            clip.ai_suggested_description = result["description"]
            clip.ai_suggested_tags = list(result["tags"])
            factors = dict(clip.viral_factors or {})
            factors["ai_hook"] = result.get("hook") or result["title"]
            factors["ai_language"] = result.get("language")
            if result.get("viral_reason"):
                factors["ai_viral_reason"] = result["viral_reason"]
            clip.viral_factors = factors
            await db.commit()
            _PREPARE_ERROR.pop(clip_id, None)
            logger.info("Metadata klip %s siap (dibuat di latar belakang).", clip_id)
    except HTTPException as exc:
        _PREPARE_ERROR[clip_id] = str(exc.detail)[:300]
        logger.warning("Persiapan metadata klip %s gagal: %s", clip_id, str(exc.detail)[:300])
    except Exception as exc:
        _PREPARE_ERROR[clip_id] = str(exc)[:300]
        logger.warning("Persiapan metadata klip %s gagal: %s", clip_id, str(exc)[:300])
    finally:
        _PREPARING.discard(clip_id)




def _metadata_response(
    clip: Clip,
    *,
    transcript: str,
    transcript_source: str,
    generated_by: str,
    ai_available: bool = True,
    status_value: str = "ready",
    message: Optional[str] = None,
    regenerate_left: Optional[int] = None,
) -> ClipMetadataResponse:
    return ClipMetadataResponse(
        clip_id=str(clip.id),
        title=clip.ai_suggested_title or "",
        description=clip.ai_suggested_description or "",
        tags=list(clip.ai_suggested_tags or []),
        hook=_hook_of(clip),
        language=None,
        transcript=transcript,
        transcript_source=transcript_source,
        generated_by=generated_by,
        ai_available=ai_available,
        status=status_value,
        message=message,
        regenerate_left=regenerate_left,
    )


@router.get("/{clip_id}", response_model=ClipDetailResponse)
async def get_clip_detail(
    clip_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Detail satu klip (video, metadata AI, transkrip) untuk popup di dashboard."""
    clip, _task = await _load_clip(db, clip_id, current_user.id)
    return ClipDetailResponse(
        id=str(clip.id),
        task_id=str(clip.task_id),
        clip_index=clip.clip_index,
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration=clip.duration,
        title=clip.title,
        download_url=clip.download_url,
        subtitle_url=clip.subtitle_url,
        thumbnail_url=clip.thumbnail_url,
        file_size=clip.file_size,
        viral_score=clip.viral_score,
        viral_factors=clip.viral_factors,
        ai_suggested_title=clip.ai_suggested_title,
        ai_suggested_description=clip.ai_suggested_description,
        ai_suggested_tags=clip.ai_suggested_tags,
        youtube_uploaded=clip.youtube_uploaded,
        youtube_video_id=clip.youtube_video_id,
        editing_applied=clip.editing_applied,
        created_at=clip.created_at,
        transcript=_stored_transcript(clip),
        youtube_video_url=(
            f"https://youtu.be/{clip.youtube_video_id}" if clip.youtube_video_id else None
        ),
    )


@router.post("/{clip_id}/metadata", response_model=ClipMetadataResponse)
async def generate_clip_metadata(
    clip_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[ClipMetadataRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Buat (atau segarkan) metadata YouTube dari transkrip klip.

    `regenerate=false` dan metadata sudah ada → langsung kembalikan cache supaya
    popup tidak memanggil AI setiap kali dibuka. Klip lama yang belum punya
    transkrip diproses di latar belakang (`status="preparing"`).
    """
    options = payload or ClipMetadataRequest()
    clip, _task = await _load_clip(db, clip_id, current_user.id)

    settings = get_settings()
    regen_limit = max(1, int(settings.AI_REGENERATE_LIMIT or 3))
    regen_used = int(
        await db.scalar(
            select(func.count())
            .select_from(AiRegenerateLog)
            .where(AiRegenerateLog.clip_id == clip.id)
        )
        or 0
    )
    regen_left = max(0, regen_limit - regen_used)

    if options.regenerate and regen_left <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Regenerate limit reached ({regen_limit}× per clip). "
                "Edit the title/description/tags manually instead."
            ),
        )

    if not options.regenerate and clip.ai_suggested_title:
        return _metadata_response(
            clip,
            transcript=_stored_transcript(clip),
            transcript_source="stored",
            generated_by="ai",
            regenerate_left=regen_left,
        )

    stored = _stored_transcript(clip)
    if len(stored.split()) < MIN_TRANSCRIPT_WORDS:
        failure = _PREPARE_ERROR.get(clip.id)
        if failure and not options.regenerate:
            return _metadata_response(
                clip,
                transcript="",
                transcript_source="unavailable",
                generated_by="ai",
                status_value="failed",
                message=(
                    "This clip has no transcript, so no metadata was created: "
                    f"{failure}"
                ),
                regenerate_left=regen_left,
            )
        if options.regenerate:
            _PREPARE_ERROR.pop(clip.id, None)
        # Transkripsi klip bisa memakan >100 detik (batas timeout Cloudflare),
        # jadi jalankan di latar belakang dan minta klien menanyakan lagi.
        if clip.id not in _PREPARING:
            _PREPARING.add(clip.id)
            background_tasks.add_task(_prepare_metadata_bg, clip.id, current_user.id)
        return _metadata_response(
            clip,
            transcript="",
            transcript_source="preparing",
            generated_by="ai",
            status_value="preparing",
            message=(
                "Preparing the clip transcript (SRT/Whisper); AI metadata follows. "
                "This usually takes 1-2 minutes."
            ),
            regenerate_left=regen_left,
        )

    # Regenerate memakai model khusus (OpenRouter gpt-6-luna); pembuatan pertama
    # memakai AI_MODEL global.
    generator = MetadataGenerator(
        model=settings.AI_REGENERATE_MODEL if options.regenerate else None
    )
    try:
        result = await generator.generate(
            transcript=stored,
            source_title=clip.title or "",
            duration=float(clip.duration or 0),
            start_time=clip.start_time or "",
            end_time=clip.end_time or "",
            language=options.language,
            variation=1 if options.regenerate else 0,
        )
    except MetadataGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    clip.ai_suggested_title = result["title"][:500]
    clip.ai_suggested_description = result["description"]
    clip.ai_suggested_tags = list(result["tags"])

    # `hook` disimpan di viral_factors agar kartu klip bisa menampilkannya tanpa
    # memanggil AI lagi.
    factors = dict(clip.viral_factors or {})
    factors["ai_hook"] = result.get("hook") or result["title"]
    factors["ai_language"] = result.get("language")
    clip.viral_factors = factors

    if options.regenerate:
        db.add(
            AiRegenerateLog(
                clip_id=clip.id,
                user_id=current_user.id,
                model=generator.model,
            )
        )
        regen_left = max(0, regen_left - 1)

    await db.commit()
    await db.refresh(clip)

    return _metadata_response(
        clip,
        transcript=stored,
        transcript_source="stored",
        generated_by="ai",
        ai_available=generator.available,
        regenerate_left=regen_left,
    )


@router.patch("/{clip_id}/metadata", response_model=ClipMetadataResponse)
async def update_clip_metadata(
    clip_id: str,
    payload: ClipMetadataUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Simpan judul/deskripsi/tag hasil edit pengguna (tanpa memanggil AI)."""
    clip, _task = await _load_clip(db, clip_id, current_user.id)

    settings = get_settings()
    regen_limit = max(1, int(settings.AI_REGENERATE_LIMIT or 3))
    regen_used = int(
        await db.scalar(
            select(func.count())
            .select_from(AiRegenerateLog)
            .where(AiRegenerateLog.clip_id == clip.id)
        )
        or 0
    )
    regen_left = max(0, regen_limit - regen_used)

    clip.ai_suggested_title = payload.title.strip()[:500]
    clip.ai_suggested_description = payload.description.strip()
    clip.ai_suggested_tags = _clean_tags(payload.tags)
    await db.commit()
    await db.refresh(clip)

    return _metadata_response(
        clip,
        transcript=_stored_transcript(clip),
        transcript_source="stored",
        generated_by="manual",
        regenerate_left=regen_left,
    )

