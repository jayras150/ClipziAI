"""
YouTube schemas - Upload, metadata, viral score
"""
from typing import Optional, List
from pydantic import BaseModel


class YouTubeMetadata(BaseModel):
    title: str
    description: str
    tags: List[str] = []
    category_id: str = "22"
    privacy_status: str = "public"
    made_for_kids: bool = False


class YouTubeUploadRequest(BaseModel):
    task_id: Optional[str] = None
    clip_id: str
    metadata: Optional[YouTubeMetadata] = None
    auto_generate_metadata: bool = True
    # Privasi default saat metadata tidak dikirim dari popup klip.
    privacy_status: Optional[str] = "public"
    # Upload ulang walau klip ini sudah pernah diunggah.
    force: bool = False


class YouTubeUploadResponse(BaseModel):
    success: bool
    youtube_video_id: Optional[str] = None
    youtube_video_url: Optional[str] = None
    error: Optional[str] = None
    title: Optional[str] = None
    privacy_status: Optional[str] = None
    already_uploaded: bool = False


class YouTubeAuthUrl(BaseModel):
    auth_url: str


class YouTubeConnectionStatus(BaseModel):
    connected: bool
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    message: Optional[str] = None


class ViralScoreResponse(BaseModel):
    clip_id: str
    score: float
    factors: dict
    recommended_title: str
    recommended_tags: List[str]
    reasoning: str