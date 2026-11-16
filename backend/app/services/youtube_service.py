"""
YouTube Service - OAuth2, Data API v3 upload
"""
import asyncio
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Any, List, Optional
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.services.youtube_metadata import build_snippet, normalize_privacy

settings = get_settings()
logger = logging.getLogger(__name__)

# Callback progres: (persen 0-100, byte terkirim, total byte).
ProgressCallback = Callable[[int, int, int], None]


class _ProgressFile:
    """File-like object yang melaporkan progres baca ke requests.

    Dipakai untuk upload resumable YouTube agar UI bisa menampilkan bar 0-100%
    tanpa mengubah cara requests mengirim body (Content-Length tetap akurat).
    """

    def __init__(
        self,
        path: str,
        total: int,
        callback: Optional[ProgressCallback],
        base_percent: int = 40,
        span_percent: int = 59,
    ) -> None:
        self._handle = open(path, "rb")
        self._total = max(1, int(total))
        self._callback = callback
        self._base = max(0, min(100, int(base_percent)))
        self._span = max(0, min(100 - self._base, int(span_percent)))
        self._sent = 0
        self._last_percent = -1

    def __len__(self) -> int:
        return self._total

    def read(self, size: int = -1) -> bytes:
        data = self._handle.read(size)
        if not data:
            return data
        self._sent += len(data)
        percent = self._base + int(self._span * self._sent / self._total)
        percent = max(0, min(99, percent))
        if percent != self._last_percent:
            self._last_percent = percent
            self._report(percent)
        return data

    def _report(self, percent: int) -> None:
        if self._callback is None:
            return
        try:
            self._callback(percent, self._sent, self._total)
        except Exception:
            # Progres tidak boleh menggagalkan upload.
            pass

    def close(self) -> None:
        self._handle.close()

    def __getattr__(self, name: str):
        return getattr(self._handle, name)


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
                    "YouTube is not configured yet. An administrator must set "
                    "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and "
                    "YOUTUBE_REDIRECT_URI in the server environment."
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
                    detail=f"Google rejected the YouTube authorization: {response.text[:300]}",
                )
            payload = response.json()
            if not payload.get("access_token"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Google did not return a YouTube access token.",
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
                    detail=f"Could not read the YouTube channel: {response.text[:300]}",
                )
            items = response.json().get("items", [])
            if not items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This Google account has no usable YouTube channel.",
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
                    "The YouTube token expired and no refresh token is available. "
                    "Reconnect your YouTube account from the Profile or Dashboard page."
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
                        "Could not refresh the YouTube token. Reconnect your "
                        f"YouTube account. ({response.text[:200]})"
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
        publish_at: Optional[datetime] = None,
        progress_callback: Optional[ProgressCallback] = None,
        thumbnail_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Upload video ke YouTube memakai resumable upload Data API v3.

        Sumber video boleh file lokal (`video_path`, dipakai worker) atau URL
        publik R2 (`source_url`, dipakai API saat pengguna klik upload).
        """
        if not video_path and not source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No video source available (empty file and URL).",
            )

        allowed_privacy = {"public", "unlisted", "private"}
        privacy = privacy_status if privacy_status in allowed_privacy else "public"
        if publish_at is not None:
            # YouTube mensyaratkan video private saat publishAt dikirim.
            privacy = "private"
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
            publish_at,
            progress_callback,
            thumbnail_url,
        )


    @staticmethod
    def _set_thumbnail(access_token: str, video_id: str, thumbnail_url: str) -> Dict[str, Any]:
        """Pasang thumbnail kustom (16:9 JPEG). Mengembalikan status + pesan error."""
        result: Dict[str, Any] = {"ok": False, "error": None}
        try:
            headers = {"User-Agent": "ClipziAI-Backend/1.0"}
            image = requests.get(thumbnail_url, headers=headers, timeout=30)
            if image.status_code not in (200, 206) or not image.content:
                message = f"Thumbnail klip tidak bisa diunduh (status={image.status_code})"
                logger.warning(message)
                result["error"] = message
                return result
            payload = image.content
            try:
                # YouTube butuh 16:9: thumbnail 9:16 dikonversi (center-crop) di sini.
                from app.services import thumbnail_render

                payload = thumbnail_render.to_landscape(payload)
            except Exception:  # noqa: BLE001 - fallback ke bytes asli
                payload = image.content
            response = requests.post(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                params={"videoId": video_id, "uploadType": "media"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "image/jpeg",
                },
                data=payload,
                timeout=60,
            )
            if not response.ok:
                detail = YouTubeService._google_error(response)
                logger.warning("YouTube menolak thumbnail %s: %s", video_id, detail)
                result["error"] = detail
                result["code"] = YouTubeService.classify_thumbnail_error(detail)
                return result
            result["ok"] = True
            return result
        except Exception as exc:  # noqa: BLE001 - thumbnail tidak boleh menggagalkan upload
            logger.warning("Gagal memasang thumbnail %s: %s", video_id, exc)
            result["error"] = str(exc)[:300]
            return result

    @staticmethod
    def classify_thumbnail_error(message: str) -> str:
        """Klasifikasikan error `thumbnails.set` agar UI bisa menampilkan saran."""
        text = (message or "").lower()
        if "permissions to upload and set custom video thumbnails" in text:
            return "thumbnail_permission"
        if "media too large" in text or "too large" in text:
            return "thumbnail_too_large"
        if "unsupported image" in text or "invalid image" in text:
            return "thumbnail_invalid"
        return ""

    @staticmethod
    def _google_error(response: requests.Response) -> str:
        """Ambil pesan error asli dari Google (JSON) agar UI bisa menampilkannya."""
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            text = (response.text or "").strip()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "html" in content_type or text.startswith("<"):
                # Google mengirim halaman HTML untuk body request yang ditolak di
                # lapisan frontend (mis. panjang body tidak cocok).
                return (
                    "Google returned an HTML error page instead of JSON "
                    f"(HTTP {response.status_code}) — usually the upload body length "
                    "did not match or the session URL expired."
                )
            return text[:300]
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = error.get("message") or ""
            errors = error.get("errors") or []
            reason = errors[0].get("reason") if errors and isinstance(errors[0], dict) else ""
            detail = " ".join(part for part in (reason, message) if part)
            return (detail or str(payload))[:300]
        return str(error or payload)[:300]

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
        publish_at: Optional[datetime] = None,
        progress_callback: Optional[ProgressCallback] = None,
        thumbnail_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bagian sinkron dari resumable upload (dijalankan di thread)."""

        def report(percent: int, sent: int = 0, total: int = 0) -> None:
            if progress_callback is None:
                return
            try:
                progress_callback(max(0, min(100, int(percent))), int(sent), int(total))
            except Exception:
                pass

        report(1)
        snippet = build_snippet(
            title=title,
            description=description,
            tags=tags or [],
            category_id=category_id,
        )
        privacy = normalize_privacy(privacy)
        logger.info(
            "YouTube upload: title=%r tags=%s category=%s privacy=%s",
            snippet["title"][:60],
            len(snippet["tags"]),
            snippet["categoryId"],
            privacy,
        )

        status_payload: Dict[str, Any] = {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(made_for_kids),
        }
        if publish_at is not None:
            try:
                normalized = publish_at
                if normalized.tzinfo is None:
                    normalized = normalized.replace(tzinfo=timezone.utc)
                status_payload["publishAt"] = (
                    normalized.astimezone(timezone.utc)
                    .isoformat(timespec="seconds")
                    .replace("+00:00", "Z")
                )
            except Exception:
                status_payload.pop("publishAt", None)

        init_response = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
            },
            json={
                "snippet": snippet,
                "status": status_payload,
            },
            timeout=60,
        )
        if not init_response.ok:
            reason = self._google_error(init_response)
            logger.warning(
                "YouTube rejected upload session (status=%s): %s | title=%r tags=%s category=%s",
                init_response.status_code,
                reason,
                snippet["title"][:80],
                snippet["tags"],
                snippet["categoryId"],
            )
            if init_response.status_code in (401, 403):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "YouTube rejected the upload session. Reconnect your YouTube "
                        f"account and try again. ({reason})"
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"YouTube rejected the upload metadata: {reason}",
            )

        upload_url = init_response.headers.get("Location")
        if not upload_url:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube did not return an upload URL.",
            )
        report(10)

        handle = None
        temp_path = None
        try:
            # Unduh dulu ke berkas sementara: Google menolak (HTTP 400 HTML) bila
            # Content-Length tidak persis sama dengan body yang terkirim, dan itu
            # mudah terjadi saat streaming langsung dari URL R2.
            if video_path:
                source_path = video_path
            else:
                if not source_url:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No video URL was provided for the upload.",
                    )
                fd, source_path = tempfile.mkstemp(prefix="yt-upload-", suffix=".mp4")
                os.close(fd)
                temp_path = source_path
                with requests.get(source_url, stream=True, timeout=600) as download:
                    download.raise_for_status()
                    try:
                        download_total = int(download.headers.get("Content-Length") or 0)
                    except (TypeError, ValueError):
                        download_total = 0
                    downloaded = 0
                    with open(source_path, "wb") as out:
                        for piece in download.iter_content(chunk_size=1024 * 1024):
                            if piece:
                                out.write(piece)
                                downloaded += len(piece)
                                if download_total > 0:
                                    report(
                                        10 + int(25 * downloaded / download_total),
                                        downloaded,
                                        download_total,
                                    )
                                else:
                                    report(min(34, 10 + downloaded // (1024 * 1024)), downloaded, 0)

            content_length = os.path.getsize(source_path)
            if content_length <= 0:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="The video size could not be determined, so the upload was cancelled.",
                )
            report(40, 0, content_length)

            progress_handle = _ProgressFile(
                source_path,
                content_length,
                progress_callback,
                base_percent=40,
                span_percent=59,
            )
            handle = progress_handle
            put_response = requests.put(
                upload_url,
                data=progress_handle,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(content_length),
                    "Content-Range": f"bytes 0-{content_length - 1}/{content_length}",
                },
                timeout=3600,
            )
            logger.info(
                "YouTube upload sent %s bytes -> status %s",
                content_length,
                put_response.status_code,
            )
        finally:
            if handle:
                handle.close()
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        if put_response.status_code not in (200, 201):
            reason = self._google_error(put_response)
            if put_response.status_code in (401, 403):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "YouTube rejected the video upload. Reconnect your YouTube "
                        f"account and try again. ({reason})"
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"YouTube upload failed ({put_response.status_code}): {reason}",
            )

        payload = put_response.json()
        video_id = payload.get("id")
        if not video_id:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="YouTube did not return a video id.",
            )
        report(100, content_length, content_length)
        if thumbnail_url:
            thumb_result = self._set_thumbnail(access_token, str(video_id), thumbnail_url)
            if not thumb_result.get("ok"):
                logger.warning(
                    "Thumbnail otomatis gagal untuk %s: %s", video_id, thumb_result.get("error")
                )
        return {
            "success": True,
            "video_id": video_id,
            "video_url": f"https://youtu.be/{video_id}",
            "privacy_status": privacy,
        }

