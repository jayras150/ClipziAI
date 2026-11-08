"""
Video Downloader Service - yt-dlp wrapper with cookie support
"""
import os
import re
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class VideoDownloader:
    """Download videos from YouTube, TikTok, Instagram, Facebook, Vimeo using yt-dlp."""
    
    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_url(self, url: str) -> bool:
        """Validate if URL is from a supported platform."""
        supported_domains = [
            "youtube.com", "youtu.be", "tiktok.com",
            "instagram.com", "facebook.com", "vimeo.com",
        ]
        return any(domain in url for domain in supported_domains)
    
    def detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        elif "tiktok.com" in url_lower:
            return "tiktok"
        elif "instagram.com" in url_lower:
            return "instagram"
        elif "facebook.com" in url_lower:
            return "facebook"
        elif "vimeo.com" in url_lower:
            return "vimeo"
        return "unknown"
    
    async def get_video_info(self, url: str, cookies_path: Optional[str] = None) -> Dict[str, Any]:
        """Get video metadata without downloading."""
        import yt_dlp
        
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
        }
        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_info, url, ydl_opts)
    
    def _extract_info(self, url: str, ydl_opts: dict) -> Dict[str, Any]:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "platform": self.detect_proactively(info),
                "thumbnail": info.get("thumbnail"),
            }
    
    def detect_proactively(self, info: dict) -> str:
        """Detect platform from yt-dlp info dict."""
        extractor = info.get("extractor", "")
        if "youtube" in extractor:
            return "youtube"
        elif "tiktok" in extractor:
            return "tiktok"
        elif "instagram" in extractor:
            return "instagram"
        elif "facebook" in extractor:
            return "facebook"
        elif "vimeo" in extractor:
            return "vimeo"
        return "unknown"
    
    async def download_video(
        self,
        url: str,
        output_filename: str,
        cookies_path: Optional[str] = None,
        quality: str = "720",
    ) -> str:
        """Download video and return local file path."""
        import yt_dlp
        
        output_path = str(self.download_dir / output_filename)
        
        ydl_opts = {
            "format": f"bestvideo[height<={quality}]+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
        }
        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = cookies_path
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._download, url, ydl_opts)
        
        # Find the downloaded file
        for ext in ["mp4", "mkv", "webm"]:
            path = f"{self.download_dir / output_filename}.{ext}"
            if os.path.exists(path):
                return path
        return f"{output_path}.mp4"
    
    def _download(self, url: str, ydl_opts: dict):
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])