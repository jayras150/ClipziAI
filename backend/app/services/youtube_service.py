"""
YouTube Service - OAuth2, Data API v3 upload
"""
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()

# Cache hasil preflight OAuth (redirect URI terdaftar atau tidak) selama 5 menit.
PREFLIGHT_TTL_SECONDS = 300
_PREFLIGHT_CACHE: Dict[str, Any] = {}


class YouTubeService:
    """YouTube Data API v3 integration for OAuth and video upload."""
    
    def __init__(self):
        self.client_id = settings.YOUTUBE_CLIENT_ID
        self.client_secret = settings.YOUTUBE_CLIENT_SECRET
        self.redirect_uri = settings.YOUTUBE_REDIRECT_URI
        self.api_key = settings.YOUTUBE_API_KEY

    def ensure_oauth_configured(self) -> None:
        """Ensure server-owned Google OAuth credentials are configured."""
        if not self.client_id or not self.client_secret or not self.redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "YouTube belum dikonfigurasi. Administrator harus mengisi "
                    "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, dan "
                    "YOUTUBE_REDIRECT_URI di environment server."
                ),
            )
    
    def get_auth_url(self, state: str) -> str:
        """Generate Google OAuth2 authorization URL."""
        self.ensure_oauth_configured()
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

    def preflight(self, auth_url: str) -> Optional[str]:
        """
        Cek apakah Google menerima konfigurasi OAuth kita SEBELUM user diarahkan.

        Tanpa ini, pengguna hanya melihat halaman error Google
        ("Error 400: redirect_uri_mismatch") tanpa tahu penyebabnya.
        Mengembalikan None bila OK, atau kode masalah:
        "redirect_uri_mismatch" / "invalid_client" / "network".

        Hasil di-cache 5 menit supaya klik berikutnya tidak menunggu Google.
        """
        global _PREFLIGHT_CACHE
        now = time.monotonic()
        cached = _PREFLIGHT_CACHE.get("value")
        if cached and now - _PREFLIGHT_CACHE.get("at", 0) < PREFLIGHT_TTL_SECONDS:
            return cached

        try:
            response = requests.get(
                auth_url,
                timeout=8,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (ClipzyAI preflight)"},
            )
        except requests.RequestException:
            return "network"

        body = response.text or ""
        problem: Optional[str] = None
        if "redirect_uri_mismatch" in body:
            problem = "redirect_uri_mismatch"
        elif "invalid_client" in body or "unauthorized_client" in body:
            problem = "invalid_client"

        _PREFLIGHT_CACHE = {"value": problem, "at": now}
        return problem


    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Exchange OAuth2 code for access/refresh tokens."""
        self.ensure_oauth_configured()

        def request_tokens() -> Dict[str, Any]:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
            if not response.ok:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google menolak otorisasi YouTube: {response.text[:300]}",
                )
            payload = response.json()
            if not payload.get("access_token"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google tidak mengembalikan access token YouTube.",
                )
            return payload

        return await asyncio.to_thread(request_tokens)

    async def get_channel(self, access_token: str) -> Dict[str, str]:
        """Read the authenticated user's primary YouTube channel."""
        def request_channel() -> Dict[str, str]:
            response = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "id,snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if not response.ok:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Gagal membaca channel YouTube: {response.text[:300]}",
                )
            items = response.json().get("items", [])
            if not items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Akun Google ini belum memiliki channel YouTube yang dapat digunakan.",
                )
            channel = items[0]
            return {
                "channel_id": channel["id"],
                "channel_name": channel.get("snippet", {}).get("title", "YouTube Channel"),
            }

        return await asyncio.to_thread(request_channel)

    @staticmethod
    def token_expiry(expires_in: Any) -> datetime:
        """Convert OAuth expires_in to a timezone-aware database timestamp."""
        return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in or 3600))
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Tukar refresh token dengan access token baru (token Google ~1 jam)."""
        self.ensure_oauth_configured()
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "Token YouTube sudah kedaluwarsa dan tidak ada refresh token. "
                    "Hubungkan ulang akun YouTube dari halaman Profil/Dashboard."
                ),
            )

        def call_google() -> Dict[str, Any]:
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=30,
            )
            if not response.ok:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "Gagal memperbarui token YouTube. Hubungkan ulang akun "
                        f"YouTube. ({response.text[:200]})"
                    ),
                )
            return response.json()

        return await asyncio.to_thread(call_google)

    async def upload_video(
        self,
        access_token: str,
        video_path: Optional[str] = None,
        title: str = "",
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = "public",
        category_id: str = "24",
        made_for_kids: bool = False,
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload video ke YouTube memakai resumable upload Data API v3.

        Sumber video boleh file lokal (`video_path`, dipakai worker) atau URL
        publik R2 (`source_url`, dipakai API saat pengguna klik upload).
        """
        if not video_path and not source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sumber video tidak tersedia (file maupun URL kosong).",
            )

        allowed_privacy = {"public", "unlisted", "private"}
        privacy = privacy_status if privacy_status in allowed_privacy else "public"
        return await asyncio.to_thread(
            self._upload_sync,
            access_token,
            video_path,
            title,
            description,
            tags,
            privacy,
            category_id,
            made_for_kids,
            source_url,
        )

    def _upload_sync(
        self,
        access_token: str,
        video_path: Optional[str],
        title: str,
        description: str,
        tags: Optional[List[str]],
        privacy: str,
        category_id: str,
        made_for_kids: bool,
        source_url: Optional[str],
    ) -> Dict[str, Any]:
        """Bagian sinkron dari resumable upload (dijalankan di thread)."""
        init_response = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
            },
            json={
                "snippet": {
                    "title": (title or "Shorts")[:100],
                    "description": (description or "")[:4900],
                    "tags": [str(tag)[:60] for tag in (tags or [])][:15],
                    "categoryId": str(category_id or "24"),
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": bool(made_for_kids),
                },
            },
            timeout=60,
        )
        if not init_response.ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"YouTube menolak sesi upload: {init_response.text[:400]}",
            )

        upload_url = init_response.headers.get("Location")
        if not upload_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube tidak mengembalikan URL upload.",
            )

        handle = None
        download = None
        try:
            if video_path:
                handle = open(video_path, "rb")
                content_length = os.path.getsize(video_path)

                def file_chunks():
                    while True:
                        piece = handle.read(1024 * 1024)
                        if not piece:
                            break
                        yield piece

                body = file_chunks()
            else:
                download = requests.get(source_url, stream=True, timeout=180)
                download.raise_for_status()
                content_length = int(download.headers.get("Content-Length") or 0)

                def url_chunks():
                    for piece in download.iter_content(chunk_size=1024 * 1024):
                        if piece:
                            yield piece

                body = url_chunks()

            if content_length <= 0:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Ukuran file video tidak diketahui; upload dibatalkan.",
                )

            put_response = requests.put(
                upload_url,
                data=body,
                headers={"Content-Type": "video/mp4", "Content-Length": str(content_length)},
                timeout=3600,
            )
        finally:
            if handle:
                handle.close()
            if download is not None:
                download.close()

        if put_response.status_code not in (200, 201):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Upload ke YouTube gagal ({put_response.status_code}): "
                    f"{put_response.text[:400]}"
                ),
            )

        payload = put_response.json()
        video_id = payload.get("id")
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube tidak mengembalikan video id.",
            )
        return {
            "success": True,
            "video_id": video_id,
            "video_url": f"https://youtu.be/{video_id}",
            "privacy_status": privacy,
        }

