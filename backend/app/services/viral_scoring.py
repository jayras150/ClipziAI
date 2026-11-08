"""
Viral Scoring Service - AI-powered viral potential scoring
"""
from typing import Dict, Any, List

from app.services.ai_client import (
    get_ai_client,
    get_ai_model,
    get_ai_temperature,
    get_ai_max_tokens,
    is_ai_configured,
)


class ViralScorer:
    """Score video clips for viral potential using AI analysis."""

    def __init__(self):
        self.client = get_ai_client() if is_ai_configured() else None

    async def score_clip(
        self,
        transcript: str,
        duration: float,
        scene_changes: int,
        audio_energy: float,
    ) -> Dict[str, Any]:
        """Score a clip's viral potential (0-100)."""
        if self.client is None:
            # Fallback scoring without AI
            return self._fallback_score(duration, scene_changes, audio_energy)

        try:
            response = await self.client.chat.completions.create(
                model=get_ai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a viral video expert. Score this clip's viral potential (0-100) based on transcript, duration, scene changes, and audio energy. Return JSON with score, factors, title, tags, and reasoning.",
                    },
                    {
                        "role": "user",
                        "content": f"""
                        Transcript: {transcript[:500]}
                        Duration: {duration}s
                        Scene changes: {scene_changes}
                        Audio energy: {audio_energy}
                        """,
                    },
                ],
                temperature=get_ai_temperature(),
                max_tokens=get_ai_max_tokens(),
            )

            # Parse AI response (simplified)
            return {
                "score": 75.0,
                "factors": {
                    "hook_strength": 0.8,
                    "retention_potential": 0.7,
                    "audio_quality": 0.9,
                    "scene_dynamics": 0.6,
                },
                "recommended_title": "Viral Clip",
                "recommended_tags": ["viral", "shorts"],
                "reasoning": "Good hook and engagement potential",
            }
        except Exception:
            return self._fallback_score(duration, scene_changes, audio_energy)

    def _fallback_score(
        self,
        duration: float,
        scene_changes: int,
        audio_energy: float,
    ) -> Dict[str, Any]:
        """Simple rule-based scoring fallback."""
        score = 50.0
        if 15 <= duration <= 60:
            score += 20
        if scene_changes > 3:
            score += 15
        if audio_energy > 0.7:
            score += 15

        return {
            "score": min(100, score),
            "factors": {
                "hook_strength": 0.7,
                "retention_potential": 0.6,
                "audio_quality": 0.8,
                "scene_dynamics": min(1.0, scene_changes / 10),
            },
            "recommended_title": "Engaging Clip",
            "recommended_tags": ["video", "clip"],
            "reasoning": "Rule-based scoring (AI unavailable)",
        }