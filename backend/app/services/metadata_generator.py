"""
Metadata Generator - judul, deskripsi, dan tag YouTube yang benar-benar
mengikuti isi video.

Sumber kebenaran satu-satunya adalah **transkrip klip** hasil Whisper (pipeline
menyimpannya di `clips.viral_factors.transcript`). Prompt memaksa model:

  * hanya memakai fakta/pernyataan yang ada di transkrip,
  * menyebut topik yang benar-benar diucapkan (bukan topik karangan),
  * tidak memakai kalimat template ("Watch this amazing short clip!",
    "Created with Clipzi AI", dsb.),
  * membalas JSON valid tanpa teks tambahan.

Sengaja **tidak ada fallback template**: bila AI tidak dikonfigurasi, balasannya
tidak valid, atau judulnya tidak nyambung dengan transkrip, kita melempar
`MetadataGenerationError` agar API memberi pesan jelas. Lebih baik pengguna
melihat error daripada menerima metadata palsu.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.ai_client import get_ai_client, get_ai_model, is_ai_configured

logger = logging.getLogger(__name__)

# Transkrip di bawah ini dianggap tidak cukup untuk membuat metadata yang jujur.
MIN_TRANSCRIPT_WORDS = 6
MAX_TITLE_LENGTH = 100          # batas keras YouTube
MAX_DESCRIPTION_LENGTH = 4800   # batas YouTube 5000, sisakan ruang hashtag
MAX_TAGS = 12
MIN_TITLE_LENGTH = 18           # judul lebih pendek dari ini tidak berfungsi sebagai hook
MIN_COPIED_WORDS = 7            # judul yang menyalin 7+ kata berurutan dari transkrip ditolak

# Frasa template yang dilarang muncul (indikasi AI tidak membaca transkrip).
BANNED_PHRASES = (
    "watch this amazing",
    "amazing short clip",
    "created with clipzi",
    "clipzi ai",
    "viral short video",
    "don't forget to like and subscribe",
    "jangan lupa like dan subscribe",
)

# Kata umum yang tidak membuktikan keterkaitan judul dengan isi video.
STOPWORDS = {
    "yang", "dan", "atau", "untuk", "dengan", "dari", "pada", "itu", "ini",
    "adalah", "akan", "juga", "kita", "kamu", "saya", "aku", "dia", "mereka",
    "tapi", "tetapi", "kalau", "jika", "karena", "supaya", "agar", "bisa",
    "tidak", "belum", "sudah", "masih", "saja", "lagi", "sangat", "paling",
    "the", "and", "for", "with", "that", "this", "you", "your", "are", "was",
    "have", "has", "from", "they", "them", "his", "her", "its", "our", "not",
    "but", "what", "when", "why", "how", "all", "can", "will", "just",
}

# Tag terlalu umum: boleh, tapi tidak boleh jadi satu-satunya isi.
GENERIC_TAGS = {
    "viral", "shorts", "short", "trending", "fyp", "foryou", "video", "clip",
    "reels", "tiktok", "youtubeshorts", "youtube", "content", "konten",
}

SYSTEM_PROMPT = (
    "You are a senior short-form video editor who writes YouTube Shorts metadata "
    "that earns clicks without lying. You receive the Whisper transcript of ONE "
    "clip.\n\n"
    "HARD RULES\n"
    "1. Use ONLY facts stated in the transcript. Never invent names, brands, "
    "numbers, places or claims.\n"
    "2. NEVER copy a sentence from the transcript verbatim as the title. Rewrite it "
    "into a hook: keep the specific claim/number/promise, drop the filler opener.\n"
    "3. Title: 40-90 characters (hard max 100), sentence case, no quotes, no ALL "
    "CAPS, no emoji spam (max 1). It must contain the single most surprising or "
    "useful idea of the clip.\n"
    "4. Hook: max 80 characters, the on-screen opening line. Punchier than the "
    "title, still true to the transcript.\n"
    "5. Description: 2-4 sentences. Sentence 1 = the payoff/insight. Sentence 2-3 = "
    "context from the transcript. Then a short CTA, then 3-5 hashtags.\n"
    "6. Tags: 8-12 lowercase, specific (topics, objects, activities actually "
    "mentioned). At most 2 generic tags (shorts, viral).\n"
    "7. No template wording: never write 'watch this amazing clip', 'created with "
    "Clipzi', 'don't forget to like and subscribe'.\n"
    "8. viral_reason: one sentence (max 25 words) explaining WHY this moment can "
    "stop the scroll (tension, surprise, number, contrarian take, practical tip).\n"
    "9. language: ISO-639-1 of the dominant transcript language (id, en, ...).\n\n"
    "OUTPUT: only valid JSON, no prose:\n"
    '{"title": string, "description": string, "tags": string[], "hook": string, '
    '"viral_reason": string, "language": string}\n\n'
    "EXAMPLES\n"
    "Bad title (transcript dump): 'jadi gini guys saya mau kasih tips budgeting "
    "yang benar buat anak muda'\n"
    "Good title: 'Budgeting Rule That Saved Me 40% of My Salary'\n"
    "Bad title (clickbait, not in transcript): 'This ONE Trick Makes You a "
    "Millionaire in 24 Hours'\n"
    "Good title: 'Why Your 50/30/20 Budget Keeps Failing'\n"
    "Bad hook: 'Halo semuanya, kembali lagi di channel ini'\n"
    "Good hook: 'Your budget fails because of this one line item.'"
)


class MetadataGenerationError(RuntimeError):
    """Metadata berbasis transkrip tidak bisa dibuat (AI mati / hasil melenceng)."""


def _significant_words(text: str) -> set[str]:
    """Kata bermakna dari sebuah teks (untuk cek grounding)."""
    cleaned = re.sub(r"[^0-9a-zA-Z\u00c0-\u024f\s]", " ", (text or "").lower())
    # Minimal 3 huruf supaya kata pendek bermakna seperti "mie"/"cat" tetap ikut.
    return {word for word in cleaned.split() if len(word) >= 3 and word not in STOPWORDS}


def _extract_json(raw: str) -> Dict[str, Any]:
    """Ambil objek JSON pertama dari balasan model (termasuk blok ```json)."""
    text = (raw or "").strip()
    if not text:
        raise MetadataGenerationError("AI returned an empty response.")
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise MetadataGenerationError("AI response is not JSON.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MetadataGenerationError(f"AI returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise MetadataGenerationError("AI JSON is not an object.")
    return payload


def _clean_tags(raw: Any) -> List[str]:
    """Normalisasi tag: huruf kecil, tanpa '#', unik, maksimal 12."""
    if not isinstance(raw, list):
        raw = [raw] if isinstance(raw, str) else []
    tags: List[str] = []
    for item in raw:
        tag = re.sub(r"[^0-9a-z\u00c0-\u024f\s-]", "", str(item).strip().lower().lstrip("#"))
        tag = re.sub(r"\s+", " ", tag).strip()
        if not tag or len(tag) > 30 or tag in tags:
            continue
        tags.append(tag)
    return tags[:MAX_TAGS]


FILLER_PREFIXES = (
    "jadi", "nah", "oke", "ok", "ya", "kan", "hmm", "eh", "well", "so",
    "like", "you know", "gitu", "begini",
)


def _clean_sentence(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    cleaned = re.sub(r"^[-\u2013\u2014\u2022*\s]+", "", cleaned)
    words = cleaned.split()
    while words and re.sub(r"[^\w]", "", words[0]).lower() in FILLER_PREFIXES:
        words.pop(0)
    return " ".join(words).strip(" ,;:-")


def _split_sentences(value: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", str(value or "").strip())
    return [part for part in (_clean_sentence(p) for p in parts) if len(part.split()) >= 3]


EXTRA_STOPWORDS = {
    "sampai", "setiap", "butuh", "harus", "bikin", "bilang", "gitu", "kayak",
    "sperti", "seperti", "dalam", "sama", "lebih", "banyak", "orang", "waktu",
}


def _top_keywords(value: str, limit: int = 8) -> List[str]:
    counts: Dict[str, int] = {}
    for raw in re.findall(r"[A-Za-z\u00c0-\u00ff]{4,}", value or ""):
        word = raw.lower()
        if word in STOPWORDS or word in GENERIC_TAGS or word in EXTRA_STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0])))
    return [word for word, _ in ranked[:limit]]


def build_heuristic_metadata(
    transcript: str,
    *,
    duration: float,
    start_time: str = "",
    end_time: str = "",
    source_title: str = "",
) -> Dict[str, Any]:
    """Metadata berkualitas dari transkrip saat LLM tidak tersedia/gagal.

    Tidak memakai kalimat template: judul diambil dari kalimat pertama yang
    benar-benar diucapkan, deskripsi = kalimat awal + akhir, tag = kata kunci
    yang paling sering muncul. Timestamp disimpan terpisah (bukan di judul).
    """
    text = re.sub(r"\s+", " ", str(transcript or "")).strip()
    sentences = _split_sentences(text)
    keywords = _top_keywords(text)
    first = sentences[0] if sentences else _clean_sentence(text)
    last = sentences[-1] if len(sentences) > 1 else ""

    title = first[:70].strip(" ,;:-.").strip()
    if title:
        title = title[0].upper() + title[1:]
    if len(title.split()) < 3:
        title = (source_title or " ".join(keywords[:3]) or "Key moment").strip()
    if not title:
        title = "Clip %s-%s" % (start_time or "0:00", end_time or "")

    description_parts = [first] if first else []
    if last and last != first:
        description_parts.append(last)
    description = " ".join(description_parts).strip()
    if keywords:
        extra = "Key topics: %s." % ", ".join(keywords[:5])
        if extra.lower() not in description.lower():
            description = (description + " " + extra).strip()
    if not description:
        description = title

    tags = list(dict.fromkeys(keywords[:8] + ["shorts"]))[:MAX_TAGS]

    return {
        "title": title[:MAX_TITLE_LENGTH],
        "description": description[:MAX_DESCRIPTION_LENGTH],
        "tags": tags,
        "hook": (first or title)[:80],
        "viral_reason": None,
        "language": None,
        "variation": 0,
        "heuristic": True,
        "start_time": start_time,
        "end_time": end_time,
        "duration": round(float(duration or 0), 2),
    }


class MetadataGenerator:
    """Buat metadata YouTube yang grounded ke transkrip klip."""

    def __init__(
        self,
        *,
        client: Optional[Any] = None,
        model: Optional[str] = None,
    ) -> None:
        """Generator metadata.

        `client`/`model` opsional: worker mengirim client yang menunjuk ke
        llama-server lokal (Qwen3-4B-Instruct-2507), sedangkan API memakai
        konfigurasi global (OpenRouter untuk tombol Regenerate).
        """
        if client is not None:
            self.client = client
            self.model = model or "local-llm"
            self.available = True
        else:
            self.available = is_ai_configured()
            self.client = get_ai_client() if self.available else None
            self.model = model or get_ai_model()

    def ensure_ready(self) -> None:
        """Lempar error jelas bila AI belum dikonfigurasi di server."""
        if not self.available or self.client is None:
            raise MetadataGenerationError(
                "AI is not configured on the server (set AI_PROVIDER/AI_API_KEY). "
                "No metadata was generated to avoid inventing content."
            )

    async def generate(
        self,
        *,
        transcript: str,
        source_title: str = "",
        duration: float = 0.0,
        start_time: str = "",
        end_time: str = "",
        language: Optional[str] = None,
        variation: int = 0,
    ) -> Dict[str, Any]:
        """
        Hasilkan metadata dari transkrip klip.

        `variation` dipakai saat pengguna menekan "generate ulang" supaya model
        tidak mengembalikan kalimat yang persis sama.
        """
        self.ensure_ready()
        text = (transcript or "").strip()
        words = text.split()
        if len(words) < MIN_TRANSCRIPT_WORDS:
            raise MetadataGenerationError(
                "The clip transcript is too short to ground the metadata. "
                "Reprocess the video with Whisper transcription enabled."
            )

        # Transkrip panjang dipotong agar tetap cepat & murah, tapi bagian awal
        # dan akhir dipertahankan karena biasanya berisi hook dan kesimpulan.
        if len(text) > 6000:
            text = f"{text[:3600]}\n...\n{text[-2200:]}"

        keywords = _top_keywords(text, limit=10)
        opening = " ".join(text.split()[:30])
        user_prompt = (
            f"Clip transcript (Whisper, {len(words)} words, duration "
            f"{duration:.1f}s, range {start_time}-{end_time}):\n"
            f'"""\n{text}\n"""\n\n'
            f"Source video title: {source_title or '(unknown)'}\n"
            f"Opening line (first ~3 seconds): {opening}\n"
            f"Recurring content words: {', '.join(keywords) or '(none)'}\n"
            f"Output language: {language or 'match the transcript language'}\n\n"
            "Task: turn this moment into Shorts metadata. Rewrite the core idea into "
            "a hook-driven title (never paste a transcript sentence), give the "
            "on-screen hook, a description with 3-5 hashtags, 8-12 specific tags, and "
            "one sentence explaining why the moment can stop the scroll.\n"
        )
        if variation:
            user_prompt += (
                f"\nAttempt #{variation + 1}: use a different angle and different "
                "wording from the previous version, still grounded in the transcript.\n"
            )

        last_error: Optional[Exception] = None
        # 3 percobaan: model kadang membalas kosong (GLM/OpenRouter) dan sebagian
        # provider menolak `response_format`, jadi percobaan terakhir tanpa itu.
        for attempt in range(3):
            request_kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": (0.35, 0.6, 0.45)[attempt],
                "max_tokens": 900,
            }
            if attempt < 2:
                request_kwargs["response_format"] = {"type": "json_object"}
            try:
                response = await self.client.chat.completions.create(**request_kwargs)  # type: ignore[union-attr]
                content = response.choices[0].message.content or ""
                payload = _extract_json(content)
                return self._validate(payload, transcript=text, variation=variation)
            except MetadataGenerationError as exc:
                last_error = exc
                logger.warning("Metadata AI ditolak (percobaan %s): %s", attempt + 1, exc)
            except Exception as exc:  # provider error, timeout, dsb.
                last_error = exc
                logger.warning("Metadata AI gagal (percobaan %s): %s", attempt + 1, str(exc)[:300])

        raise MetadataGenerationError(
            "AI could not produce metadata from the transcript (empty or truncated response). "
            f"Please try again. Detail: {str(last_error)[:200]}"
        )

    def _validate(
        self,
        payload: Dict[str, Any],
        *,
        transcript: str,
        variation: int,
    ) -> Dict[str, Any]:
        """Bersihkan + pastikan hasil AI benar-benar nyambung dengan transkrip."""
        title = re.sub(r"\s+", " ", str(payload.get("title") or "")).strip().strip('"')
        description = str(payload.get("description") or "").strip()
        hook = re.sub(r"\s+", " ", str(payload.get("hook") or "")).strip()
        language = str(payload.get("language") or "").strip().lower()[:5] or None
        tags = _clean_tags(payload.get("tags"))

        if not title:
            raise MetadataGenerationError("AI did not produce a title.")
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH].rstrip()

        # --- Anti "transcript dump": judul tidak boleh menyalin kalimat transkrip.
        normalized_transcript = " ".join(re.sub(r"[^\w\s]", " ", transcript.lower()).split())
        normalized_title = " ".join(re.sub(r"[^\w\s]", " ", title.lower()).split())
        title_tokens = normalized_title.split()
        if len(title_tokens) >= MIN_COPIED_WORDS:
            for start in range(0, max(0, len(title_tokens) - MIN_COPIED_WORDS) + 1):
                window = " ".join(title_tokens[start : start + MIN_COPIED_WORDS])
                if window and window in normalized_transcript:
                    raise MetadataGenerationError(
                        "The AI title is copied verbatim from the transcript "
                        f"({MIN_COPIED_WORDS}+ words). It was rejected so a real hook "
                        "is written instead."
                    )
        if len(title) < MIN_TITLE_LENGTH:
            raise MetadataGenerationError(
                f"The AI title is too short ({len(title)} chars) to work as a hook."
            )

        lowered = f"{title} {description}".lower()
        for phrase in BANNED_PHRASES:
            if phrase in lowered:
                raise MetadataGenerationError("AI used template wording, so the metadata was rejected.")

        if not description:
            raise MetadataGenerationError("AI did not produce a description.")
        description = description[:MAX_DESCRIPTION_LENGTH]

        # --- Grounding: judul wajib berbagi kata bermakna dengan transkrip.
        transcript_lower = transcript.lower()
        transcript_words = _significant_words(transcript)
        title_words = _significant_words(title)
        if transcript_words and not (title_words & transcript_words):
            raise MetadataGenerationError(
                "The AI title does not match the transcript, so the metadata was rejected."
            )

        # --- Tag: minimal 3 yang benar-benar muncul di transkrip/judul/deskripsi.
        corpus = transcript_words | title_words | _significant_words(description)
        grounded = [
            tag for tag in tags
            if (set(tag.split()) & corpus) or tag in transcript_lower
        ]
        if len(grounded) < 3:
            raise MetadataGenerationError(
                "The AI tags are too generic or unrelated to the video, so the metadata was rejected."
            )
        if all(tag in GENERIC_TAGS for tag in grounded):
            raise MetadataGenerationError("All tags are generic, so the metadata was rejected.")

        if not hook:
            hook = title

        viral_reason = re.sub(
            r"\s+", " ", str(payload.get("viral_reason") or "")
        ).strip()[:240]

        return {
            "title": title,
            "description": description,
            "tags": grounded,
            "hook": hook[:80],
            "viral_reason": viral_reason or None,
            "language": language,
            "variation": variation,
        }

