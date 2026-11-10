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
    "Kamu adalah editor short-form video profesional yang menulis metadata "
    "YouTube Shorts berdasarkan transkrip video.\n"
    "ATURAN WAJIB:\n"
    "1. Kamu HANYA boleh memakai informasi yang tertulis di transkrip. Jangan "
    "menambah nama orang, merek, angka, tempat, atau klaim yang tidak ada.\n"
    "2. Judul harus menyebut topik/aksi utama yang benar-benar diucapkan dan "
    "membuat orang ingin menonton, tanpa clickbait bohong. 40-90 karakter, "
    "maksimal 100 karakter, tanpa tanda kutip dan tanpa ALL CAPS.\n"
    "3. Deskripsi: 2-4 kalimat yang merangkum isi cuplikan + 1 ajakan singkat, "
    "lalu diakhiri 3-5 hashtag relevan. Dilarang memakai kalimat template.\n"
    "4. Tag: 8-12 tag huruf kecil, spesifik (nama topik, benda, aktivitas yang "
    "disebut di transkrip). Tag generik seperti 'shorts' maksimal 2.\n"
    "5. Balas HANYA JSON valid dengan skema: "
    '{"title": string, "description": string, "tags": string[], '
    '"hook": string, "language": string}\n'
    "6. 'hook' = kalimat pembuka video (maks 80 karakter) dari ide utama "
    "transkrip, dipakai sebagai overlay teks di kartu klip.\n"
    "7. 'language' = kode ISO-639-1 bahasa dominan transkrip (contoh: id, en)."
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
        raise MetadataGenerationError("AI membalas kosong.")
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise MetadataGenerationError("Balasan AI bukan JSON.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MetadataGenerationError(f"JSON dari AI tidak valid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise MetadataGenerationError("JSON dari AI bukan objek.")
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


class MetadataGenerator:
    """Buat metadata YouTube yang grounded ke transkrip klip."""

    def __init__(self) -> None:
        self.available = is_ai_configured()
        self.client = get_ai_client() if self.available else None
        self.model = get_ai_model()

    def ensure_ready(self) -> None:
        """Lempar error jelas bila AI belum dikonfigurasi di server."""
        if not self.available or self.client is None:
            raise MetadataGenerationError(
                "AI belum dikonfigurasi di server (isi AI_PROVIDER/AI_API_KEY). "
                "Metadata tidak dibuat agar tidak asal-asalan."
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
                "Transkrip klip terlalu pendek untuk dijadikan dasar metadata. "
                "Proses ulang video dengan transkripsi Whisper aktif."
            )

        # Transkrip panjang dipotong agar tetap cepat & murah, tapi bagian awal
        # dan akhir dipertahankan karena biasanya berisi hook dan kesimpulan.
        if len(text) > 6000:
            text = f"{text[:3600]}\n...\n{text[-2200:]}"

        user_prompt = (
            f"Transkrip klip (Whisper, {len(words)} kata, durasi "
            f"{duration:.1f} detik, rentang {start_time}-{end_time}):\n"
            f'"""\n{text}\n"""\n\n'
            f"Judul video sumber: {source_title or '(tidak diketahui)'}\n"
            f"Bahasa yang diminta: {language or 'ikuti bahasa transkrip'}\n"
        )
        if variation:
            user_prompt += (
                f"\nIni percobaan ke-{variation + 1}: pakai sudut pandang dan "
                "pilihan kata yang berbeda dari versi sebelumnya, tetapi tetap "
                "hanya berdasarkan transkrip di atas.\n"
            )

        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                response = await self.client.chat.completions.create(  # type: ignore[union-attr]
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.35 if attempt == 0 else 0.6,
                    max_tokens=900,
                    response_format={"type": "json_object"},
                )
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
            f"Gagal membuat metadata dari transkrip: {str(last_error)[:240]}"
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
            raise MetadataGenerationError("AI tidak menghasilkan judul.")
        if len(title) > MAX_TITLE_LENGTH:
            title = title[:MAX_TITLE_LENGTH].rstrip()

        lowered = f"{title} {description}".lower()
        for phrase in BANNED_PHRASES:
            if phrase in lowered:
                raise MetadataGenerationError("AI memakai kalimat template; metadata ditolak.")

        if not description:
            raise MetadataGenerationError("AI tidak menghasilkan deskripsi.")
        description = description[:MAX_DESCRIPTION_LENGTH]

        # --- Grounding: judul wajib berbagi kata bermakna dengan transkrip.
        transcript_lower = transcript.lower()
        transcript_words = _significant_words(transcript)
        title_words = _significant_words(title)
        if transcript_words and not (title_words & transcript_words):
            raise MetadataGenerationError(
                "Judul dari AI tidak nyambung dengan isi transkrip; metadata ditolak."
            )

        # --- Tag: minimal 3 yang benar-benar muncul di transkrip/judul/deskripsi.
        corpus = transcript_words | title_words | _significant_words(description)
        grounded = [
            tag for tag in tags
            if (set(tag.split()) & corpus) or tag in transcript_lower
        ]
        if len(grounded) < 3:
            raise MetadataGenerationError(
                "Tag dari AI terlalu umum / tidak terkait isi video; metadata ditolak."
            )
        if all(tag in GENERIC_TAGS for tag in grounded):
            raise MetadataGenerationError("Semua tag generik; metadata ditolak.")

        if not hook:
            hook = title

        return {
            "title": title,
            "description": description,
            "tags": grounded,
            "hook": hook[:80],
            "language": language,
            "variation": variation,
        }

