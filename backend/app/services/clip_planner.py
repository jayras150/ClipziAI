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
    return round(max(0.0, min(100.0, value)), 1)


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
        has_subtitle=True,
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

    total = score + hook_bonus + payoff_bonus + filler_penalty + density_bonus + cohesion_bonus + fit_bonus
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
    if len(sentences) < 2:
        return []

    speech = SpeechMap(words, sentences, silences, total_duration)
    quota = int(quota or plan_clip_quota(total_duration))
    quota = max(1, min(quota, len(sentences)))

    soft_min = max(20.0, float(target_min) * 0.92)
    soft_max = max(soft_min + 5.0, float(target_max) * 1.25)
    min_gap = max(8.0, float(target_min) * 0.5)

    skip_intro_outro = total_duration > 180.0
    candidates: List[Dict[str, Any]] = []

    for i, start_sentence in enumerate(sentences):
        if _is_filler_start(start_sentence):
            continue
        seen_starts: set[float] = set()
        for j in range(i, len(sentences)):
            end_sentence = sentences[j]
            raw_duration = end_sentence.end - start_sentence.start
            if raw_duration > soft_max:
                break
            if raw_duration < soft_min:
                continue
            if not end_sentence.closes or end_sentence.ends_with_connector:
                continue

            start = speech.refine_start(start_sentence.start)
            end = speech.refine_end(end_sentence.end)
            if start in seen_starts:
                continue
            seen_starts.add(start)

            duration = end - start
            if duration < soft_min * 0.95 or duration > soft_max * 1.08:
                continue
            if skip_intro_outro and (start < 2.0 or end > total_duration - 2.0):
                continue

            scored = score_candidate(speech, start, end, target_min, target_max)
            factors = scored["factors"]
            factors["first_sentence"] = start_sentence.text[:280]
            factors["last_sentence"] = end_sentence.text[:280]
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
