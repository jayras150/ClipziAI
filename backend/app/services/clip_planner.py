"""
Clip planner — memilih momen viral yang benar-benar utuh kalimatnya.

Alur:
  segmen transkrip (dengan timestamp kata)
    → peta ucapan (SpeechMap)
    → kandidat: setiap AWAL kalimat × setiap AKHIR kalimat yang utuh
    → skor (hook, retensi, emosi, payoff, kohesi topik, filler, batas kalimat)
    → stratified pick: timeline dibagi per kuota supaya klip tersebar merata
    → daftar rentang siap render (durasi apa adanya, boleh 1:03 / 1:16)

Kuota klip mengikuti panjang video sumber:

  ≤ 15 menit          → 3
  15 → 30 menit       → 3 … 6
  30 → 60 menit       → 6 … 8
  60 → 120 menit      → 8 … 10
  > 120 menit         → 10
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.speech_boundaries import (
    FILLERS,
    PAYOFF_WORDS,
    Sentence,
    SpeechMap,
    Word,
    build_sentences,
    extract_words,
)
from app.services.viral import POWER_WORDS, score_clip

SECOND_PERSON = {"kamu", "kalian", "anda", "lo", "lu", "kau", "you", "your"}

_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "itu", "ini", "ada", "untuk", "dengan",
    "saya", "aku", "kamu", "dia", "kita", "kami", "mereka", "juga", "bisa",
    "akan", "sudah", "belum", "tidak", "bukan", "saja", "atau", "tapi", "kalau",
    "the", "a", "an", "is", "are", "was", "and", "or", "to", "of", "in", "it",
}


def plan_clip_quota(source_seconds: float) -> int:
    """Jumlah klip yang wajar untuk panjang video sumber."""
    minutes = max(0.0, float(source_seconds or 0.0) / 60.0)
    if minutes <= 15:
        return 3
    if minutes <= 30:
        return int(round(3 + (minutes - 15) * (3 / 15)))
    if minutes <= 60:
        return int(round(6 + (minutes - 30) * (2 / 30)))
    if minutes <= 120:
        return int(round(8 + (minutes - 60) * (2 / 60)))
    return 10


def _clamp_score(value: float) -> float:
    # Plafon 96 supaya skor tidak pernah "sempurna" dan antar klip tetap bisa
    # dibedakan di UI.
    return round(max(0.0, min(96.0, value)), 1)


def _content_words(words: Sequence[Word]) -> List[str]:
    return [
        w.clean for w in words
        if w.clean and len(w.clean) > 2 and w.clean not in _STOPWORDS
    ]


def _cohesion(words: Sequence[Word]) -> float:
    """0..1 — seberapa besar klip membahas satu topik (kata berulang)."""
    content = _content_words(words)
    if len(content) < 8:
        return 0.3
    unique = set(content)
    repeated = len(content) - len(unique)
    return round(min(1.0, repeated / max(4.0, len(unique) * 0.55)), 3)


def _filler_ratio(words: Sequence[Word]) -> float:
    if not words:
        return 0.0
    hits = sum(1 for w in words if w.clean in FILLERS)
    return round(hits / len(words), 3)


def _is_filler_start(sentence: Sentence) -> bool:
    if not sentence.words:
        return False
    return sentence.words[0].clean in FILLERS


def score_candidate(
    speech: SpeechMap,
    start: float,
    end: float,
    target_min: float,
    target_max: float,
) -> Dict[str, Any]:
    """Skor 0..100 + faktor penjelas untuk satu kandidat rentang."""
    duration = max(0.1, end - start)
    words = speech.words_between(start, end)
    text = " ".join(w.text for w in words).strip()
    base = score_clip(
        transcript=text,
        duration=duration,
        has_subtitle=False,  # subtitle baru dibuat setelah render
        has_caption=False,
        target_range=(target_min, target_max),
    )
    score = float(base["score"])
    factors: Dict[str, Any] = dict(base["factors"])

    hook_text = " ".join(w.text for w in words[:16]).lower()
    hook_bonus = 0.0
    if "?" in hook_text:
        hook_bonus += 6.0
    if re.search(r"\d", hook_text):
        hook_bonus += 4.0
    if any(w.clean in POWER_WORDS for w in words[:22]):
        hook_bonus += 6.0
    if any(w.clean in SECOND_PERSON for w in words[:22]):
        hook_bonus += 4.0
    if words and words[0].clean in FILLERS:
        hook_bonus -= 12.0

    last_sentence = speech.trailing_sentence(end, tolerance=0.5)
    payoff_bonus = 0.0
    if last_sentence is not None:
        if last_sentence.closes:
            payoff_bonus += 4.0
        if last_sentence.ends_with_connector:
            payoff_bonus -= 10.0
        last_words = {w.clean for w in last_sentence.words}
        if last_words & PAYOFF_WORDS:
            payoff_bonus += 6.0

    filler_penalty = -min(8.0, _filler_ratio(words) * 45.0)
    speech_ratio = round(speech.speech_seconds(start, end) / duration, 3)
    density_bonus = 4.0 if speech_ratio >= 0.62 else (-4.0 if speech_ratio < 0.35 else 0.0)
    cohesion = _cohesion(words)
    cohesion_bonus = round(cohesion * 6.0, 1)

    ideal = (target_min + target_max) / 2
    deviation = abs(duration - ideal) / max(1.0, ideal)
    fit_bonus = round(max(-6.0, 4.0 - deviation * 10.0), 1)

    total = score + (hook_bonus + payoff_bonus + filler_penalty + density_bonus + cohesion_bonus + fit_bonus) * 0.55
    ok, notes = speech.validate(start, end)

    factors.update(
        {
            "label": base["factors"].get("label"),
            "hook_bonus": round(hook_bonus, 1),
            "payoff_bonus": round(payoff_bonus, 1),
            "filler_penalty": round(filler_penalty, 1),
            "cohesion": cohesion,
            "speech_ratio": speech_ratio,
            "boundary_ok": ok,
            "boundary_notes": notes,
        }
    )
    return {"score": _clamp_score(total), "factors": factors, "transcript": text}


def _build_units(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Satuan ucapan = segmen Whisper (sudah VAD-aligned, berakhir di jeda).

    Segmen sangat panjang dipecah agar titik potong tetap tersedia; segmen
    pendek yang jedanya hampir nol digabung supaya tidak memotong frasa.
    """
    units: List[Dict[str, Any]] = []
    for segment in segments or []:
        try:
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or start)
        except (TypeError, ValueError):
            continue
        text = str(segment.get("text") or "").strip()
        words = extract_words([segment])
        if end <= start or len(words) < 2:
            continue
        if units and start - units[-1]["end"] < 0.22:
            units[-1]["end"] = max(units[-1]["end"], end)
            units[-1]["text"] = (units[-1]["text"] + " " + text).strip()
            units[-1]["words"].extend(words)
            continue
        units.append({"start": start, "end": end, "text": text, "words": words})

    # Pecah unit > 18 detik (maks 3 bagian) supaya titik potong tetap rapat.
    expanded: List[Dict[str, Any]] = []
    for unit in units:
        duration = unit["end"] - unit["start"]
        if duration <= 18.0 or len(unit["words"]) < 8:
            expanded.append(unit)
            continue
        parts = max(2, min(3, int(round(duration / 9.0))))
        chunk = max(1, len(unit["words"]) // parts)
        for index in range(parts):
            subset = unit["words"][index * chunk: (index + 1) * chunk if index < parts - 1 else None]
            if len(subset) < 2:
                continue
            expanded.append(
                {
                    "start": subset[0].start,
                    "end": subset[-1].end,
                    "text": " ".join(word.text for word in subset),
                    "words": subset,
                }
            )
    return expanded


def _looks_repetitive(words: Sequence[Word]) -> bool:
    """Deteksi halusinasi Whisper (kata berulang terus-menerus)."""
    if len(words) < 14:
        return False
    unique = len({w.clean for w in words if w.clean})
    return unique / max(1, len(words)) < 0.32


_BAD_FIRST = {
    "sih", "kan", "nah", "gitu", "gini", "kayak", "kaya", "terus", "lalu",
    "dan", "tapi", "karena", "atau", "sama", "yaudah", "ya", "nih", "tuh",
}


def _bad_start(words: Sequence[Word]) -> bool:
    """Awal klip tidak boleh partikel/gumaman ('sih', 'kan', 'eee')."""
    if not words:
        return True
    first = words[0].clean
    return first in FILLERS or first in _BAD_FIRST


def _overlaps(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def _select_stratified(
    candidates: Sequence[Dict[str, Any]],
    quota: int,
    total_duration: float,
    min_gap: float,
) -> List[Dict[str, Any]]:
    """Ambil klip terbaik per bucket timeline supaya hasilnya tersebar."""
    if quota <= 0:
        return []
    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(quota)]
    span = max(1.0, float(total_duration or 1.0))
    for candidate in candidates:
        index = int(candidate["start"] / span * quota)
        index = max(0, min(quota - 1, index))
        buckets[index].append(candidate)

    chosen: List[Dict[str, Any]] = []

    def acceptable(candidate: Dict[str, Any]) -> bool:
        for picked in chosen:
            if _overlaps(candidate, picked):
                return False
            if abs(candidate["start"] - picked["start"]) < min_gap:
                return False
        return True

    for bucket in buckets:
        for candidate in sorted(bucket, key=lambda c: -c["score"]):
            if acceptable(candidate):
                chosen.append(candidate)
                break

    if len(chosen) < quota:
        for candidate in sorted(candidates, key=lambda c: -c["score"]):
            if len(chosen) >= quota:
                break
            if acceptable(candidate):
                chosen.append(candidate)

    chosen.sort(key=lambda c: c["start"])
    return chosen[:quota]


def plan_clips(
    segments: Sequence[Dict[str, Any]],
    silences: Sequence[Tuple[float, float]],
    total_duration: float,
    target_min: float = 60.0,
    target_max: float = 90.0,
    quota: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Rentang klip terbaik. Kosong bila transkrip tidak tersedia (fallback)."""
    words = extract_words(segments)
    if len(words) < 12:
        return []
    sentences = build_sentences(words)
    speech = SpeechMap(words, sentences, silences, total_duration)

    units = _build_units(segments)
    if len(units) < 3:
        return []

    quota = int(quota or plan_clip_quota(total_duration))
    quota = max(1, min(quota, len(units) // 2 or 1))

    # Batas bawah HARAM di bawah 60 detik: klip harus > 1 menit.
    hard_min = max(60.0, float(target_min))
    soft_min = hard_min
    soft_max = max(soft_min + 10.0, float(target_max) * 1.25)
    min_gap = max(20.0, float(target_min) * 0.6)

    skip_intro_outro = total_duration > 180.0
    candidates: List[Dict[str, Any]] = []

    for i, first_unit in enumerate(units):
        if _bad_start(first_unit["words"]):
            continue
        seen_starts: set[float] = set()
        for j in range(i, len(units)):
            last_unit = units[j]
            raw_duration = last_unit["end"] - first_unit["start"]
            if raw_duration > soft_max:
                break
            if raw_duration < soft_min:
                continue

            start = speech.refine_start(first_unit["start"])
            end = speech.refine_end(last_unit["end"])
            if start in seen_starts:
                continue
            seen_starts.add(start)

            duration = end - start
            if duration < hard_min or duration > soft_max * 1.08:
                continue
            if skip_intro_outro and (start < 2.0 or end > total_duration - 2.0):
                continue
            # Wajib: tidak memotong satu kata pun.
            ok, notes = speech.validate(start, end)
            if not ok:
                continue
            span_words = speech.words_between(start, end)
            if _looks_repetitive(span_words):
                continue
            if speech.speech_seconds(start, end) / max(1.0, duration) < 0.32:
                continue

            scored = score_candidate(speech, start, end, target_min, target_max)
            factors = scored["factors"]
            factors["first_sentence"] = str(first_unit["text"])[:280]
            factors["last_sentence"] = str(last_unit["text"])[:280]
            candidates.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(duration, 2),
                    "score": scored["score"],
                    "factors": factors,
                    "transcript": scored["transcript"][:1200],
                }
            )

    if not candidates:
        return []
    return _select_stratified(candidates, quota, total_duration, min_gap)
