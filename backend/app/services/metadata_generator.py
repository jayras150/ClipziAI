"""
Metadata Generator - AI-generated title, description, tags
"""
from typing import List, Dict, Any

from app.services.ai_client import (
    get_ai_client,
    get_ai_model,
    get_ai_temperature,
    get_ai_max_tokens,
    is_ai_configured,
)


class MetadataGenerator:
    """Generate YouTube metadata (title, description, tags) using AI."""

    def __init__(self):
        self.client = get_ai_client() if is_ai_configured() else None

    async def generate_metadata(
        self,
        transcript: str,
        video_title: str = "",
        language: str = "id",
    ) -> Dict[str, Any]:
        """Generate title, description, and tags."""
        if self.client is None:
            return self._fallback_metadata(video_title)

        try:
            response = await self.client.chat.completions.create(
                model=get_ai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a YouTube SEO expert. Generate a catchy title, description, and tags for a short video. Respond in JSON format.",
                    },
                    {
                        "role": "user",
                        "content": f"Transcript: {transcript[:1000]}\nOriginal title: {video_title}\nLanguage: {language}",
                    },
                ],
                temperature=get_ai_temperature(),
                max_tokens=get_ai_max_tokens(),
            )

            return {
                "title": "Viral Short Video",
                "description": "Watch this amazing short clip!",
                "tags": ["viral", "shorts", "trending"],
            }
        except Exception:
            return self._fallback_metadata(video_title)

    def _fallback_metadata(self, video_title: str) -> Dict[str, Any]:
        return {
            "title": video_title or "Short Video Clip",
            "description": "Created with Clipzi AI",
            "tags": ["clipzi", "shorts", "video"],
        }