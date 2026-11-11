"""Audio transcription service for local or OpenAI-compatible providers."""
import asyncio
import gc
import logging
import os
import re
import subprocess
from typing import Dict, Any, List, Optional

import openai

from app.core.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

# Penanda error kredit/kuota dari provider (OpenRouter 402, OpenAI insufficient_quota).
_BILLING_HINTS = ("402", "credit", "insufficient_quota", "quota", "billing", "payment")


def _is_billing_error(exc: BaseException) -> bool:
    """True bila error berasal dari kredit/kuota provider (tidak akan pulih)."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(hint in text for hint in _BILLING_HINTS)


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

    def _is_gpu(self) -> bool:
        return self.provider in {"gpu", "cuda", "transformers", "hf"}

    @staticmethod
    def _cuda_available() -> bool:
        """
        True bila ada GPU CUDA yang bisa dipakai.

        Menggunakan CTranslate2 (dipakai faster-whisper) sebagai deteksi — tidak
        butuh torch. Kegagalan impor/library CUDA (mis. libcudnn tidak ketemu)
        dicatat sekali supaya penyebab fallback ke CPU kelihatan di log worker.
        """
        try:
            import ctranslate2
        except Exception as exc:
            logger.warning("CTranslate2 tidak tersedia (%s) — GPU tidak bisa dipakai", exc)
            return False
        try:
            count = int(ctranslate2.get_cuda_device_count())
        except Exception as exc:
            logger.warning(
                "Deteksi CUDA gagal (%s) — cek LD_LIBRARY_PATH libcudnn/libcublas", exc
            )
            return False
        if count <= 0:
            logger.warning("CTranslate2 tidak melihat GPU CUDA (count=0)")
        return count > 0

    @staticmethod
    def _map_gpu_model(name: str) -> str:
        """Petakan nama model HuggingFace ke nama model faster-whisper.

        Contoh: 'openai/whisper-large-v3'        -> 'large-v3'
                'openai/whisper-large-v3-turbo'  -> 'turbo'
                'large-v3'                       -> 'large-v3'
        """
        short = (name or "large-v3").split("/")[-1]
        short = short.replace("whisper-", "")
        if short.endswith("turbo"):
            return "turbo"
        return short or "large-v3"

    def _get_gpu_model(self):
        """Muat model Whisper di GPU (CTranslate2 float16), sekali saja."""
        if getattr(self, "_gpu_model", None) is not None:
            return self._gpu_model

        from faster_whisper import WhisperModel

        model_name = self._map_gpu_model(settings.GPU_WHISPER_MODEL)
        logger.info(
            "Memuat Whisper GPU: model=%s device=cuda compute_type=float16", model_name
        )
        self._gpu_model = WhisperModel(
            model_name,
            device="cuda",
            compute_type="float16",
            download_root=self._cache_dir(),
        )
        return self._gpu_model

    async def _transcribe_gpu(
        self,
        audio_path: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        """
        Transkripsi Whisper large-v3 di GPU worker (Vast.ai), tanpa biaya API.

        Memakai CTranslate2 lewat faster-whisper (float16) — jauh lebih cepat
        daripada CPU dan tidak memerlukan torch.
        """
        loop = asyncio.get_event_loop()
        model = self._get_gpu_model()
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
            "backend": "gpu",

            "duration": info.duration,
            "segments": self._split_long_segments(segments),
            # Segmen mentah (timestamp kata) untuk clip planner.
            "raw_segments": segments,

            "full_text": " ".join(seg.get("text", "") for seg in segments),
        }


    def unload_model(self) -> None:
        """Lepas model Whisper dari VRAM (dipanggil sebelum LLM lokal dimuat).

        Qwen3-4B (2,55 GB) + Whisper large-v3 (3,1 GB) tidak aman bila hidup
        bersamaan di GPU 12 GB bersama KV cache, jadi pipeline mengosongkan
        Whisper lebih dulu.
        """
        released = False
        for attr in ("_gpu_model", "_model"):
            model = getattr(self, attr, None)
            if model is not None:
                setattr(self, attr, None)
                released = True
                del model
        gc.collect()
        try:  # bila torch tersedia (tidak wajib di image worker)
            import torch  # type: ignore

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        if released:
            logger.info("Model Whisper dilepas dari VRAM")

    def _get_remote_client(self) -> openai.AsyncOpenAI:
        """Build a client for any provider implementing OpenAI audio transcriptions."""
        api_key = settings.TRANSCRIPTION_API_KEY or settings.AI_API_KEY or settings.OPENAI_API_KEY
        if not api_key:
            raise RuntimeError(
                "TRANSCRIPTION_API_KEY is required for a non-local transcription provider."
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
                    "Local transcription needs the faster-whisper package, which is not installed "
                    "by default. Run: "
                    "pip install -r requirements-whisper-local.txt — atau pakai "
                    "an API-based TRANSCRIPTION_PROVIDER (groq/openai/openrouter)."
                ) from exc
            self._model = WhisperModel(
                # Nama model faster-whisper (tiny/base/small/medium/large-v3).
                # Penting: saat provider API gagal dan fallback lokal dipakai,
                # `self.model_size` masih berisi nama model API
                # (mis. "openai/whisper-large-v3-turbo") yang bukan repo HF valid
                # untuk faster-whisper. Jadi untuk non-lokal selalu pakai
                # WHISPER_MODEL (model yang sudah dibaking ke image).
                self.model_size if self._is_local() else (settings.WHISPER_MODEL or "small"),
                device="cpu",
                compute_type="int8",
                download_root=self._cache_dir(),
            )
        return self._model

    @staticmethod
    def _cache_dir() -> Optional[str]:
        """Folder cache model (WHISPER_CACHE_DIR); None = default HuggingFace."""
        cache_dir = settings.WHISPER_CACHE_DIR
        if not cache_dir:
            return None
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            return None
        return cache_dir
    
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transkripsi audio menjadi segmen siap-subtitle.

        Provider API dicoba lebih dulu (lebih cepat). Bila gagal -- misalnya
        OpenRouter membalas 402 "maximum cost exceeds your available credits" --
        otomatis jatuh ke Whisper lokal (faster-whisper) bila paketnya ada di
        image, sehingga subtitle tetap dihasilkan tanpa kredit API.
        """
        if self._is_local():
            return await self._transcribe_local(audio_path, language)

        # GPU worker (Vast.ai): Whisper large-v3-turbo di GPU, tanpa biaya API.
        # Deteksi otomatis: kalau CUDA tersedia, GPU selalu diprioritaskan sehingga
        # tidak perlu mengubah env di Vast (API container tanpa GPU tetap memakai
        # provider API / Whisper lokal).
        cuda_ready = self._cuda_available()
        logger.info(
            "Transkripsi: provider=%s cuda=%s model=%s cache=%s",
            self.provider,
            cuda_ready,
            self.model_size,
            self._cache_dir(),
        )
        if self._is_gpu() and not cuda_ready:
            logger.error(
                "TRANSCRIPTION_PROVIDER=gpu tetapi CUDA tidak terdeteksi — "
                "transkripsi akan jatuh ke provider API/CPU (jauh lebih lambat)."
            )

        if cuda_ready and not self._is_local():
            try:
                return await self._transcribe_gpu(audio_path, language)
            except Exception as exc:
                logger.error(
                    "Transkripsi GPU gagal (%s); lanjut ke jalur berikutnya.",
                    str(exc)[:400],
                )

        # Produksi: audio TIDAK boleh dikirim ke provider luar (OpenRouter).
        # Bila GPU gagal, satu-satunya fallback adalah Whisper lokal (CPU).
        if not settings.TRANSCRIPTION_ALLOW_REMOTE:
            logger.info("TRANSCRIPTION_ALLOW_REMOTE=false → Whisper lokal (CPU) tanpa API")
            try:
                return await self._transcribe_local(audio_path, language)
            except Exception as local_exc:
                raise RuntimeError(
                    "Transcription failed: GPU Whisper unavailable and the local "
                    f"fallback failed too ({str(local_exc)[:200]})."
                ) from local_exc

        try:
            return await self._transcribe_remote(audio_path, language)
        except Exception as exc:
            logger.warning(
                "Transkripsi via provider '%s' gagal (%s); mencoba Whisper lokal.",
                self.provider,
                str(exc)[:300],
            )
            try:
                return await self._transcribe_local(audio_path, language)
            except Exception as local_exc:
                raise RuntimeError(
                    f"Transcription failed: provider '{self.provider}' error "
                    f"({str(exc)[:200]}) and the local fallback failed too "
                    f"({str(local_exc)[:200]})."
                ) from local_exc

    async def _transcribe_local(
        self,
        audio_path: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        """Transkripsi memakai faster-whisper (CPU, int8)."""
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
            "backend": "local",

            "segments": self._split_long_segments(segments),
            # Segmen mentah (timestamp kata) untuk clip planner.
            "raw_segments": segments,

            "full_text": " ".join(seg.get("text", "") for seg in segments),
        }

    async def _transcribe_remote(
        self,
        audio_path: str,
        language: Optional[str],
    ) -> Dict[str, Any]:
        """
        Transkripsi via provider OpenAI-compatible dengan strategi berlapis.

        OpenRouter menolak `response_format=verbose_json`/`json` dengan HTTP 402
        ("maximum cost exceeds your available credits") karena taksiran biayanya
        jauh lebih tinggi, padahal request TANPA `response_format` sukses dan
        murah (hanya mengembalikan teks). Karena itu dicoba berurutan:
          1. verbose_json + timestamp_granularities (segments + words)
          2. verbose_json (segments)
          3. json
          4. default (paling kompatibel)
        Bila hasil akhir hanya teks, timing subtitle disintesis.
        """
        client = self._get_remote_client()
        attempts = [
            {"response_format": "verbose_json", "timestamp_granularities": ["segment", "word"]},
            {"response_format": "verbose_json"},
            {"response_format": "json"},
            {},
        ]

        errors: List[str] = []
        payload: Optional[Dict[str, Any]] = None
        used_attempt = -1

        for index, extra in enumerate(attempts):
            try:
                with open(audio_path, "rb") as audio_file:
                    request_kwargs: Dict[str, Any] = {
                        "file": audio_file,
                        "model": self.model_size,
                        **(extra or {}),
                    }
                    if language:
                        request_kwargs["language"] = language
                    response = await client.audio.transcriptions.create(**request_kwargs)
            except Exception as exc:
                errors.append(f"percobaan {index + 1} ({extra or 'default'}): {exc}")
                logger.warning("Transkripsi %s gagal: %s", self.provider, errors[-1])
                # Error kredit/kuota tidak akan sembuh dengan format lain, dan
                # setiap percobaan bisa makan puluhan detik. Langsung jatuh ke
                # Whisper lokal agar pengguna tidak menunggu lama.
                if _is_billing_error(exc):
                    raise RuntimeError(
                        f"Provider '{self.provider}' refused the request (credit/quota): {str(exc)[:200]}"
                    ) from exc
                continue

            candidate = (
                response.model_dump() if hasattr(response, "model_dump") else dict(response)
            )
            if candidate.get("segments"):
                payload = candidate
                used_attempt = index
                break
            if candidate.get("text") and payload is None:
                payload = candidate
                used_attempt = index

        if payload is None:
            raise RuntimeError(
                f"Transcription through provider '{self.provider}' failed for every format: "
                + " | ".join(errors[:3])
            )

        segments = self._normalise_remote_segments(payload.get("segments", []))
        full_text = (payload.get("text") or "").strip()

        if not segments and full_text:
            duration = payload.get("duration") or self._audio_duration(audio_path)
            segments = self._synthesize_segments(full_text, float(duration or 0))
            logger.info(
                "Provider %s hanya mengembalikan teks (percobaan %s); timing subtitle "
                "disintesis untuk %s segmen.",
                self.provider,
                used_attempt + 1,
                len(segments),
            )

        if not full_text:
            full_text = " ".join(segment["text"] for segment in segments)

        return {
            "language": payload.get("language") or language,
            "language_probability": None,
            "duration": payload.get("duration"),
            "backend": "remote",

            "segments": self._split_long_segments(segments),
            # Segmen mentah (timestamp kata) untuk clip planner.
            "raw_segments": segments,

            "full_text": full_text.strip(),
        }

    @staticmethod
    def _split_long_segments(
        segments: List[Dict[str, Any]],
        max_chars: int = 42,
        max_duration: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """
        Pecah segmen yang terlalu panjang agar caption vertikal mudah dibaca.

        Provider kadang mengembalikan satu segmen untuk seluruh audio (12 detik
        berisi beberapa kalimat). Satu blok besar terlihat buruk saat dibakar ke
        video, jadi tiap segmen dipecah per ~42 karakter dengan timing
        proporsional terhadap panjang teks.
        """
        output: List[Dict[str, Any]] = []

        for segment in segments:
            text = (segment.get("text") or "").strip()
            try:
                start = float(segment.get("start") or 0)
                end = float(segment.get("end") or 0)
            except (TypeError, ValueError):
                start, end = 0.0, 0.0

            if not text:
                continue

            duration = max(0.001, end - start)
            if len(text) <= max_chars and duration <= max_duration:
                output.append({**segment, "id": len(output), "text": text})
                continue

            chunks: List[str] = []
            current: List[str] = []
            for word in text.split():
                current.append(word)
                if len(" ".join(current)) >= max_chars * 0.75:
                    chunks.append(" ".join(current))
                    current = []
            if current:
                chunks.append(" ".join(current))
            if not chunks:
                chunks = [text]

            weights = [max(1, len(chunk)) for chunk in chunks]
            total_weight = sum(weights)
            cursor = start

            for chunk, weight in zip(chunks, weights):
                span = duration * weight / total_weight
                chunk_start = cursor
                chunk_end = min(end, cursor + span)
                output.append(
                    {
                        "id": len(output),
                        "start": round(chunk_start, 3),
                        "end": round(chunk_end, 3),
                        "text": chunk,
                        "words": [],
                    }
                )
                cursor = chunk_end

        return output

    @staticmethod
    def _audio_duration(audio_path: str) -> float:
        """Durasi audio (detik) lewat ffprobe; 0.0 bila gagal."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return float((result.stdout or "").strip() or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _synthesize_segments(
        text: str,
        duration: float,
        max_words: int = 7,
    ) -> List[Dict[str, Any]]:
        """
        Buat segments ber-timing dari teks polos (provider tanpa timestamp).

        Teks dipecah jadi potongan pendek (maks `max_words` kata) agar enak dibaca
        sebagai caption vertikal, lalu durasi dialokasikan proporsional terhadap
        panjang karakter. Timing ini perkiraan — tetapi jauh lebih berguna
        daripada tidak ada subtitle sama sekali.
        """
        clean = " ".join((text or "").split())
        if not clean or duration <= 0:
            return []

        pieces: List[str] = []
        for part in re.split(r"(?<=[.!?])\s+", clean):
            words = part.split()
            while len(words) > max_words:
                pieces.append(" ".join(words[:max_words]))
                words = words[max_words:]
            if words:
                pieces.append(" ".join(words))

        if not pieces:
            return []

        weights = [max(1, len(piece)) for piece in pieces]
        total_weight = sum(weights)
        cursor = 0.0
        segments: List[Dict[str, Any]] = []

        for index, (piece, weight) in enumerate(zip(pieces, weights)):
            span = duration * weight / total_weight
            start = cursor
            end = min(duration, cursor + span)
            if end - start < 0.6:
                end = min(duration, start + 0.6)
            segments.append(
                {
                    "id": index,
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": piece,
                    "words": [],
                }
            )
            cursor = end

        return segments

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