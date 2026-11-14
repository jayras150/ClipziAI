"""
Task schemas - Task CRUD
"""
from typing import Optional, List, Any
from uuid import UUID

from datetime import datetime
from pydantic import BaseModel, Field, model_validator, HttpUrl


class TaskCreate(BaseModel):
    source_url: HttpUrl
    source_type: str = "youtube"
    target_duration_min: Optional[int] = None
    target_duration_max: Optional[int] = None
    whisper_model: str = "small"
    output_format: str = "mp4"
    output_resolution: str = "1080x1920"
    fps: int = 30
    editing_options: Optional[dict] = None
    auto_upload_youtube: bool = False
    # ---------- Fase 1: editing manual ----------
    start_time: Optional[float] = Field(
        None, ge=0, description="Memulai klip dari detik ke-berapa (0 = awal video)"
    )
    end_time: Optional[float] = Field(
        None, ge=0, description="Akhir klip pada detik ke-berapa (kosong = sampai akhir)"
    )
    aspect_ratio: str = Field(
        "9:16", description="9:16 (vertikal), 1:1 (persegi), atau 16:9 (landskap)"
    )
    caption_text: Optional[str] = Field(
        None, max_length=200, description="Teks caption yang dibakar ke setiap klip"
    )
    caption_style: Optional[str] = Field(
        None,
        description=(
            "Gaya subtitle: classic | gold | boxed | neon | top | center "
            "(lihat CAPTION_STYLES di services/processor.py)"
        ),
    )
    speed: Optional[float] = Field(
        1.0, ge=0.25, le=4.0, description="Kecepatan pemutaran (0.25x - 4x)"
    )
    # ---------- Fase 2: gaya & polish ----------
    filter_preset: Optional[str] = Field(
        None, description="warm | cool | cinematic | bw | vibrant | vintage"
    )
    blur_fill: bool = Field(
        False, description="Sumber landscape diisi background blur (tidak dipotong habis)"
    )
    remove_silence: bool = Field(False, description="Buang jeda/senyap (jump cuts)")
    enhance_audio: bool = Field(False, description="Denoise + normalisasi loudness")
    watermark_url: Optional[str] = Field(None, description="URL PNG logo/watermark")
    watermark_position: str = Field("bottom-right", description="top-left|top-right|bottom-left|bottom-right|center")
    watermark_opacity: float = Field(0.85, ge=0.1, le=1.0)
    watermark_scale: float = Field(0.16, ge=0.05, le=0.6)
    intro_url: Optional[str] = Field(None, description="Video intro yang ditempel di awal")
    outro_url: Optional[str] = Field(None, description="Video outro yang ditempel di akhir")
    # ---------- Auto zoom follow-speaker ----------
    auto_zoom: Optional[str] = Field(
        None, description="'speaker' = crop mengikuti wajah pembicara"
    )
    zoom_level: float = Field(
        1.0, ge=1.0, le=2.5, description="Perbesaran jendela crop saat auto zoom"
    )
    # ---------- Musik latar ----------
    music_url: Optional[str] = Field(None, description="URL musik latar (mp3/m4a)")
    music_volume: float = Field(0.22, ge=0.0, le=1.0, description="Volume musik (0-1)")
    music_ducking: bool = Field(True, description="Volume musik turun saat ada suara orang")


class TaskResponse(BaseModel):
    # id/user_id bertipe UUID, bukan str: kolom DB-nya UUID dan Pydantic v2 tidak
    # meng-coerce UUID -> str secara implisit. Kalau ditulis `str`, endpoint
    # gagal dengan ResponseValidationError (HTTP 500) padahal data tersimpan.
    # Serialisasi JSON tetap berupa string.
    id: UUID
    user_id: UUID
    source_url: str
    source_type: str
    status: str
    progress: int
    total_clips: Optional[int]
    error_message: Optional[str]
    download_status: Optional[str] = None
    error_category: Optional[str] = None
    user_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    can_retry: bool = False
    next_retry_at: Optional[datetime] = None
    auto_upload_youtube: bool
    youtube_upload_status: Optional[str]
    youtube_video_id: Optional[str]
    youtube_video_url: Optional[str]
    credits_spent: int
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _hide_technical_error(cls, data):
        """User tidak boleh menerima pesan teknis (error_message mentah).

        `user_message` adalah versi aman yang ditampilkan ke pengguna; detail
        teknis tetap tersimpan di DB dan hanya dibuka lewat endpoint admin.
        """
        if hasattr(data, "user_message"):
            values = {name: getattr(data, name, None) for name in cls.model_fields}
            values["error_message"] = getattr(data, "user_message", None)
            return values
        return data


class TaskListResponse(BaseModel):
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class ComposeRequest(BaseModel):
    """Gabungkan beberapa klip hasil task ini menjadi satu video baru."""

    clip_ids: List[UUID] = Field(..., description="Urutan klip yang digabung (minimal 2)")
    transition: str = Field("fade", description="fade | wipeleft | dissolve | none")
    transition_duration: float = Field(0.4, ge=0.1, le=2.0)
    aspect_ratio: str = Field("9:16", description="9:16 | 1:1 | 16:9")
    music_url: Optional[str] = Field(None, description="URL musik latar (mp3/m4a)")
    music_volume: float = Field(0.22, ge=0.0, le=1.0)
    music_ducking: bool = Field(True, description="Volume musik turun saat ada suara")
    watermark_url: Optional[str] = None
    watermark_position: str = "bottom-right"
    watermark_opacity: float = Field(0.85, ge=0.1, le=1.0)
    watermark_scale: float = Field(0.16, ge=0.05, le=0.6)


class SplitRequest(BaseModel):
    """Potong satu klip menjadi dua bagian."""

    clip_id: UUID
    at_time: float = Field(..., gt=0, description="Titik potong dalam detik")
