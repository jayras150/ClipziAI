"""
Clip schemas - Clip details + metadata AI (judul, deskripsi, tag)
"""
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field
from datetime import datetime


class ClipResponse(BaseModel):
    # Sama seperti TaskResponse: kolomnya UUID, jadi tipenya UUID (JSON tetap string).
    id: UUID
    task_id: UUID
    clip_index: int
    start_time: str
    end_time: str
    duration: float
    title: str
    download_url: Optional[str]
    subtitle_url: Optional[str]
    thumbnail_url: Optional[str]
    file_size: Optional[int]
    viral_score: Optional[float]
    viral_factors: Optional[dict]
    # Hasil AI yang dipakai UI untuk menjelaskan "kenapa klip ini".
    ai_hook: Optional[str] = None
    ai_viral_reason: Optional[str] = None
    ai_suggested_title: Optional[str]
    ai_suggested_description: Optional[str]
    ai_suggested_tags: Optional[List[str]]
    youtube_uploaded: bool
    youtube_video_id: Optional[str]
    editing_applied: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class ClipMetadataResponse(BaseModel):
    """Metadata YouTube satu klip + transkrip yang dipakai sebagai dasarnya."""

    clip_id: str
    title: str
    description: str
    tags: List[str] = Field(default_factory=list)
    hook: Optional[str] = None
    language: Optional[str] = None
    transcript: str = ""
    # "stored" = transkrip dari pipeline, "whisper" = ditranskripsi saat diminta
    transcript_source: str = "stored"
    # "ai" = dibuat model, "manual" = diedit pengguna
    generated_by: str = "ai"
    ai_available: bool = True
    # "ready" = metadata siap, "preparing" = transkrip klip sedang dibuat di latar
    status: str = "ready"
    message: Optional[str] = None
    # Sisa kuota tombol "Regenerate with AI" untuk klip ini (maks 3).
    regenerate_left: Optional[int] = None


class ClipMetadataRequest(BaseModel):
    """Minta AI membuat/menyegarkan metadata."""

    regenerate: bool = False
    language: Optional[str] = None


class ClipMetadataUpdate(BaseModel):
    """Simpan hasil edit manual pengguna."""

    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: List[str] = Field(default_factory=list)


class ClipDetailResponse(ClipResponse):
    """Detail satu klip untuk popup: metadata AI + transkrip yang dipakai."""

    transcript: str = ""
    youtube_video_url: Optional[str] = None


class ClipEditRequest(BaseModel):
    """Edit satu klip di tempat (tanpa membuat Task baru)."""

    trim_start: float = Field(0, ge=0)
    trim_end: Optional[float] = Field(None, ge=0)
    speed: float = Field(1.0, ge=0.25, le=4.0)
    filter_preset: Optional[str] = None
    caption_text: Optional[str] = Field(None, max_length=300)
    caption_style: Optional[str] = None
    caption_color: Optional[str] = Field(None, max_length=20)
    caption_size: Optional[float] = Field(None, ge=12, le=160)
    caption_font: Optional[str] = Field(None, max_length=20)


class ClipEditStatusResponse(BaseModel):
    status: str
    progress: int = 0
    error: Optional[str] = None
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ClipThumbnailCandidate(BaseModel):
    url: str
    at_second: float


class ClipThumbnailResponse(BaseModel):
    clip_id: str
    candidates: List[ClipThumbnailCandidate] = Field(default_factory=list)
    selected_url: Optional[str] = None
    hook: Optional[str] = None


class ClipThumbnailSelect(BaseModel):
    url: str = Field(min_length=1, max_length=1000)

