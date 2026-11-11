"""
Batas bicara (speech boundaries) — memastikan klip dipotong di tempat yang pas.

Kenapa modul ini ada: pemotongan berbasis scene detection memotong di batas
gambar, bukan batas ucapan. Hasilnya klip mulai di tengah kalimat dan berhenti
sebelum orang selesai bicara. Modul ini membangun peta ucapan dari timestamp
**kata** (Whisper word timestamps) + jeda audio (`silencedetect`), lalu:

  * hanya mengizinkan START di awal kalimat (setelah jeda / tanda baca akhir),
  * hanya mengizinkan END di akhir kalimat yang diikuti jeda,
  * memberi pre-roll 0.25 s dan tail 0.35 s supaya suku kata pertama/terakhir
    tidak terpotong,
  * memvalidasi hasil akhir: tidak ada kata yang terpotong di titik potong.

Durasi klip TIDAK dipaksa bulat. Kalau kalimat selesai di 1:03 atau 1:16, itu
yang dipakai — selama batas kalimatnya utuh.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Kata yang membuat kalimat menggantung kalau clip berhenti di situ.
TRAILING_CONNECTORS = {
    "dan", "tapi", "tetapi", "karena", "jadi", "kalau", "atau", "sama", "sambil",
    "yang", "untuk", "dengan", "terus", "lalu", "namun", "sehingga", "padahal",
    "and", "but", "because", "so", "or", "that", "with", "then", "while", "if",
}

# Gumaman di awal kalimat — tidak layak jadi pembuka klip viral.
FILLERS = {
    "eee", "ee", "ehm", "eh", "emm", "em", "hmm", "hm", "mmm", "mm", "aaa",
    "anu", "uh", "um",
}

# Kata yang biasanya menandakan payoff/penutup yang kuat.
PAYOFF_WORDS = {
    "ternyata", "akhirnya", "hasilnya", "makanya", "intinya", "kesimpulannya",
    "jadi", "tugas", "pesan", "saran", "harus", "jangan", "coba", "ikuti",
    "ingat", "penting", "kuncinya", "rahasia", "truth", "finally", "so",
}

_SENTENCE_END_RE = re.compile(r"[.!?…]['\"”’\)\]]?$")
_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿ'’\-]+")


@dataclass
class Word:
    text: str
    start: float
    end: float
    probability: float = 0.0

    @property
    def clean(self) -> str:
        return _WORD_RE.sub("", self.text.strip().lower())


@dataclass
class Sentence:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)
    closes: bool = False      # diakhiri tanda baca / jeda panjang
    gap_after: float = 99.0   # jeda ke kalimat berikutnya (detik)
    ends_with_connector: bool = False


def extract_words(segments: Sequence[Dict[str, Any]]) -> List[Word]:
    """Ambil semua kata bertimestamp dari segmen transkrip.

    Provider yang tidak mengirim `words` tetap didukung: kata diasumsikan
    tersebar merata di dalam segmennya, cukup untuk mendeteksi batas kalimat.
    """
    words: List[Word] = []
    for segment in segments or []:
        raw_words = segment.get("words") or []
        if raw_words:
            for raw in raw_words:
                item = raw.model_dump() if hasattr(raw, "model_dump") else raw
                text = str(item.get("word") or "").strip()
                try:
                    start = float(item.get("start") or 0.0)
                    end = float(item.get("end") or start)
                except (TypeError, ValueError):
                    continue
                if not text:
                    continue
                words.append(
                    Word(
                        text=text,
                        start=start,
                        end=max(start, end),
                        probability=float(item.get("probability") or 0.0),
                    )
                )
            continue

        text = str(segment.get("text") or "").strip()
        tokens = text.split()
        if not tokens:
            continue
        try:
            seg_start = float(segment.get("start") or 0.0)
            seg_end = float(segment.get("end") or seg_start)
        except (TypeError, ValueError):
            continue
        if seg_end <= seg_start:
            seg_end = seg_start + max(0.4, 0.28 * len(tokens))
        step = (seg_end - seg_start) / len(tokens)
        for index, token in enumerate(tokens):
            words.append(
                Word(
                    text=token,
                    start=seg_start + index * step,
                    end=seg_start + (index + 1) * step,
                )
            )

    words.sort(key=lambda w: w.start)
    return words


def build_sentences(words: Sequence[Word], max_words: int = 26) -> List[Sentence]:
    """Kelompokkan kata menjadi kalimat (pakai tanda baca + jeda panjang)."""
    sentences: List[Sentence] = []
    current: List[Word] = []

    def flush(gap_after: float) -> None:
        if not current:
            return
        text = " ".join(w.text for w in current).strip()
        last = current[-1]
        closes = bool(_SENTENCE_END_RE.search(last.text.strip())) or gap_after >= 0.7
        sentences.append(
            Sentence(
                start=current[0].start,
                end=last.end,
                text=text,
                words=list(current),
                closes=closes,
                gap_after=gap_after,
                ends_with_connector=last.clean in TRAILING_CONNECTORS,
            )
        )
        current.clear()

    for index, word in enumerate(words):
        current.append(word)
        nxt = words[index + 1] if index + 1 < len(words) else None
        gap = (nxt.start - word.end) if nxt else 99.0
        punctuated = bool(_SENTENCE_END_RE.search(word.text.strip()))
        if punctuated or gap >= 0.7 or len(current) >= max_words:
            flush(gap)

    flush(99.0)
    return sentences


def detect_silences(
    media_path: str,
    noise_db: float = -32.0,
    min_duration: float = 0.18,
) -> List[Tuple[float, float]]:
    """Deteksi interval senyap (detik) dari audio sebuah file media.

    Hanya audio yang didekode (`-vn`) supaya cepat bahkan untuk video 2 jam.
    Tidak pernah melempar exception: kalau ffmpeg gagal, kembalikan list kosong
    dan planner tetap jalan memakai jeda antar kata dari transkrip.
    """
    try:
        probe = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", media_path,
                "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
                "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except Exception:
        return []

    stderr = probe.stderr or ""
    starts = [float(m) for m in re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*(-?[\d.]+)", stderr)]

    silences: List[Tuple[float, float]] = []
    for index, start in enumerate(starts):
        start = max(0.0, start)
        end = ends[index] if len(ends) > index else float("inf")
        if end > start + 0.05:
            silences.append((round(start, 3), round(end, 3)))
    return silences


PRE_ROLL = 0.25
TAIL_PAD = 0.35


class SpeechMap:
    """Peta ucapan: kata + kalimat + jeda, dengan operasi snap & validasi."""

    def __init__(
        self,
        words: Sequence[Word],
        sentences: Sequence[Sentence],
        silences: Sequence[Tuple[float, float]],
        total_duration: float,
    ) -> None:
        self.words: List[Word] = sorted(words, key=lambda w: w.start)
        self.sentences: List[Sentence] = list(sentences)
        self.silences: List[Tuple[float, float]] = list(silences)
        self.total = max(0.0, float(total_duration or 0.0))

    # ---------------- lookup ----------------
    def next_word(self, t: float, tolerance: float = 0.15) -> Optional[Word]:
        for word in self.words:
            if word.start >= t - tolerance:
                return word
        return None

    def previous_word(self, t: float, tolerance: float = 0.15) -> Optional[Word]:
        found: Optional[Word] = None
        for word in self.words:
            if word.end <= t + tolerance:
                found = word
            else:
                break
        return found

    def words_between(self, start: float, end: float) -> List[Word]:
        return [w for w in self.words if w.end > start and w.start < end]

    def text_between(self, start: float, end: float) -> str:
        return " ".join(w.text for w in self.words_between(start, end)).strip()

    # ---------------- snapping ----------------
    def refine_start(self, sentence_start: float) -> float:
        """Titik mulai yang aman: pre-roll 0.25 s, tidak menabrak ucapan lain."""
        first = self.next_word(sentence_start, tolerance=0.25)
        if first is None:
            return round(max(0.0, sentence_start), 3)
        desired = max(0.0, first.start - PRE_ROLL)
        prev = self.previous_word(first.start, tolerance=0.0)
        low = (prev.end + 0.05) if prev is not None else 0.0
        high = first.start - 0.10
        if high <= low:
            # Tidak ada jeda sama sekali: pre-roll minimal, jangan potong kata.
            start = max(0.0, first.start - 0.08)
        else:
            start = min(max(desired, low), high)
        return round(max(0.0, start), 3)

    def refine_end(self, sentence_end: float) -> float:
        """Titik akhir yang aman: tail 0.35 s, berhenti sebelum kata berikutnya."""
        end = sentence_end + TAIL_PAD
        nxt = self.next_word(sentence_end + 0.02, tolerance=0.0)
        if nxt is not None:
            end = min(end, max(sentence_end, nxt.start - 0.10))
        if self.total:
            end = min(end, self.total)
        return round(max(sentence_end, end), 3)

    # ---------------- validasi ----------------
    def validate(self, start: float, end: float) -> Tuple[bool, List[str]]:
        """False bila start/end memotong sebuah kata (toleransi 20 ms)."""
        notes: List[str] = []
        for word in self.words_between(start - 0.5, end + 0.5):
            if word.start + 0.02 < start < word.end - 0.02:
                notes.append(f"start memotong kata '{word.text}'")
            if word.start + 0.02 < end < word.end - 0.02:
                notes.append(f"end memotong kata '{word.text}'")
        return (not notes, notes)

    def speech_seconds(self, start: float, end: float) -> float:
        return round(sum(
            max(0.0, min(w.end, end) - max(w.start, start))
            for w in self.words_between(start, end)
        ), 2)

    def trailing_sentence(self, end: float, tolerance: float = 0.4) -> Optional[Sentence]:
        """Kalimat terakhir yang berakhir dekat titik potong."""
        found: Optional[Sentence] = None
        for sentence in self.sentences:
            if sentence.end <= end + tolerance:
                found = sentence
            else:
                break
        return found

