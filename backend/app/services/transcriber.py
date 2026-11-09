"""Audio transcription service for local or OpenAI-compatible providers."""
import asyncio
from typing import Dict, Any, List, Optional

import openai

from app.core.config import get_settings

settings = get_settings()


class AudioTranscriber:
    """Transcribe audio locally or through an OpenAI-compatible API."""

    def __init__(self, model_size: Optional[str] = None):
        self.provider = (settings.TRANSCRIPTION_PROVIDER or "local").strip().lower()
        self.model_size = self._pick_model(model_size)
        self._model: Optional[Any] = None

    def _pick_model(self, override: Optional[str]) -> str:
        """Pilih nama model yang cocok dengan provider.

        `TRANSCRIPTION_MODEL` adalah nama model **API** (mis.
        `openai/whisper-large-v3-turbo`). Nama itu TIDAK bisa dipakai
        faster-whisper lokal karena repo HF-nya tidak berisi `model.bin`
        (error: "Unable to open file 'model.bin'"). Untuk provider lokal pakai
        `WHISPER_MODEL` (nama faster-whisper: tiny/base/small/medium/large-v3).
        """
        fallback = settings.WHISPER_MODEL or "small"
        if override:
            return override
        if self._is_local():
            return fallback
        return settings.TRANSCRIPTION_MODEL or fallback

    def _is_local(self) -> bool:
        return self.provider in {"local", "faster-whisper", "faster_whisper"}

    def _get_remote_client(self) -> openai.AsyncOpenAI:
        """Build a client for any provider implementing OpenAI audio transcriptions."""
        api_key = settings.TRANSCRIPTION_API_KEY or settings.AI_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "TRANSCRIPTION_API_KEY wajib diisi untuk provider transkripsi non-local."
            )
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=settings.TRANSCRIPTION_BASE_URL or None,
            timeout=300.0,
            max_retries=2,
        )
    
    def _get_model(self):
        """Lazy load whisper model (hanya untuk TRANSCRIPTION_PROVIDER=local)."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Transkripsi lokal butuh paket faster-whisper yang tidak dipasang "
                    "secara default. Jalankan: "
                    "pip install -r requirements-whisper-local.txt — atau pakai "
                    "TRANSCRIPTION_PROVIDER berbasis API (groq/openai/openrouter)."
                ) from exc
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model
    
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio and return a normalized subtitle-friendly response."""
        if not self._is_local():
            return await self._transcribe_remote(audio_path, language)

        model = self._get_model()
        
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            self._transcribe_sync,
            model,
            audio_path,
            language,
        )
        
        return {
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "segments": segments,
            "full_text": " ".join(seg.get("text", "") for seg in segments),
        }

    async def _transcribe_remote(
        self,
        audio_path: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        """Call an OpenAI-compatible /audio/transcriptions endpoint."""
        client = self._get_remote_client()
        try:
            with open(audio_path, "rb") as audio_file:
                # `language=None` tidak diterima SDK; kirim hanya bila diisi.
                request_kwargs: Dict[str, Any] = {
                    "file": audio_file,
                    "model": self.model_size,
                    "response_format": "verbose_json",
                    "timestamp_granularities": ["segment", "word"],
                }
                if language:
                    request_kwargs["language"] = language

                response = await client.audio.transcriptions.create(**request_kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Transkripsi melalui provider '{self.provider}' gagal: {exc}"
            ) from exc

        payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        segments = self._normalise_remote_segments(payload.get("segments", []))
        full_text = payload.get("text") or " ".join(segment["text"] for segment in segments)
        return {
            "language": payload.get("language") or language,
            "language_probability": None,
            "duration": payload.get("duration"),
            "segments": segments,
            "full_text": full_text.strip(),
        }

    @staticmethod
    def _normalise_remote_segments(raw_segments: List[Any]) -> List[Dict[str, Any]]:
        """Normalize OpenAI-compatible verbose JSON into Clipzi subtitle segments."""
        segments: List[Dict[str, Any]] = []
        for index, raw_segment in enumerate(raw_segments):
            segment = raw_segment.model_dump() if hasattr(raw_segment, "model_dump") else raw_segment
            words = []
            for raw_word in segment.get("words") or []:
                word = raw_word.model_dump() if hasattr(raw_word, "model_dump") else raw_word
                words.append({
                    "word": word.get("word", ""),
                    "start": word.get("start"),
                    "end": word.get("end"),
                    "probability": word.get("probability"),
                })
            segments.append({
                "id": segment.get("id", index),
                "start": segment.get("start", 0.0),
                "end": segment.get("end", 0.0),
                "text": segment.get("text", "").strip(),
                "words": words,
            })
        return segments
    
    def _transcribe_sync(
        self,
        model,
        audio_path: str,
        language: Optional[str],
    ):
        segments_iter, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
        )
        
        segments = []
        for segment in segments_iter:
            words = []
            if segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability,
                    })
            segments.append({
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": words,
            })
        
        return segments, info
    
    def generate_srt(self, segments: List[dict], output_path: str) -> str:
        """Generate SRT subtitle file from segments."""
        with open(output_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                start = self._format_srt_time(seg["start"])
                end = self._format_srt_time(seg["end"])
                f.write(f"{i}\n{start} --> {end}\n{seg['text']}\n\n")
        return output_path
    
    def generate_vtt(self, segments: List[dict], output_path: str) -> str:
        """Generate VTT subtitle file from segments."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for seg in segments:
                start = self._format_vtt_time(seg["start"])
                end = self._format_vtt_time(seg["end"])
                f.write(f"{start} --> {end}\n{seg['text']}\n\n")
        return output_path
    
    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"