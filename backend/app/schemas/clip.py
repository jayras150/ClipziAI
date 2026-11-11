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
