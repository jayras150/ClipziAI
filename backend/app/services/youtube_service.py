"""
YouTube Service - OAuth2, Data API v3 upload
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()


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
    
    async def upload_video(
        self,
        access_token: str,
        video_path: str,
        title: str,
        description: str = "",
        tags: list = None,
        privacy_status: str = "public",
    ) -> Dict[str, Any]:
        """Upload video to YouTube."""
        # TODO: Implement YouTube Data API v3 upload
        return {
            "success": True,
            "video_id": "placeholder_video_id",
            "video_url": "https://youtu.be/placeholder_video_id",
        }