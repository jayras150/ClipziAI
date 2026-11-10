"""
Viral scoring — heuristik deterministik (tanpa API eksternal).

Kenapa bukan LLM: skor harus selalu tersedia, cepat, dan gratis, termasuk untuk
klip lama yang belum punya skor. Sinyal yang dipakai memang tersedia di
pipeline: transkrip per klip, durasi, kepadatan bicara, kekuatan 3 detik
pertama, kata pemicu, serta ada/tidaknya subtitle & caption.

Semua faktor disimpan sebagai 0..1 supaya UI bisa menampilkan breakdown, dan
`score` 0..100 untuk badge.
"""
import re
from typing import Any, Dict, List

# Kata yang biasanya menaikkan retensi (campuran ID/EN).
POWER_WORDS = {
    "rahasia", "gratis", "jangan", "harus", "cara", "ternyata", "kesalahan", "salah",
    "tips", "trik", "cepat", "mudah", "baru", "terbaik", "paling", "wajib", "bocor",
    "viral", "cuan", "untung", "rugi", "gagal", "berhasil", "triknya", "penting",
    "secret", "free", "never", "must", "how", "why", "best", "worst", "fast", "easy",
    "new", "hack", "mistake", "truth", "proven", "instantly", "actually", "nobody",
    "everyone", "mistakes", "warning", "biggest",
}
CTA_WORDS = {
    "ikuti", "follow", "subscribe", "share", "bagikan", "komen", "comment", "like",
    "simpan", "save", "tonton", "coba",
}
HOOK_OPENERS = (
    "jangan", "stop", "ini", "ternyata", "rahasia", "cara", "kenapa", "apa", "begini",
    "how", "why", "this", "never", "stop", "nobody", "everyone",
)
SECOND_PERSON = ("kamu", "kalian", "anda", "lo", "lu", "kau", "you", "your", "kamu?")

_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ÿ']+")


def _words(text: str) -> List[str]:
    return _WORD_RE.findall(text or "")


def _ratio(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def _label(score: float) -> str:
    if score >= 80:
        return "Sangat potensial"
    if score >= 65:
        return "Potensial"
    if score >= 50:
        return "Cukup"
    return "Perlu perbaikan"


def score_clip(
    transcript: str = "",
    duration: float = 0.0,
    has_subtitle: bool = False,
    has_caption: bool = False,
    estimated: bool = False,
) -> Dict[str, Any]:
    """Hitung skor viral 0-100 + breakdown faktor (semua 0..1)."""
    words = _words(transcript)
    count = len(words)
    lower = (transcript or "").lower()
    duration = max(0.0, float(duration or 0.0))
    wps = (count / duration) if duration else 0.0
    head = " ".join(words[:14]).lower()

    # 1) Hook: 3-7 detik pertama menentukan orang berhenti scroll atau tidak.
    hook = 0.30
    if "?" in (transcript or "")[:90]:
        hook += 0.16
    if head.strip().startswith(HOOK_OPENERS):
        hook += 0.20
    if re.search(r"\b\d+([.,]\d+)?\b", head):          # angka / statistik
        hook += 0.12
    if any(w in POWER_WORDS for w in words[:25]):
        hook += 0.18
    if not words:
        hook = 0.15

    # 2) Durasi: sweet spot Shorts/Reels 18-45 detik.
    if 18 <= duration <= 45:
        fit = 1.0
    elif 12 <= duration < 18 or 45 < duration <= 60:
        fit = 0.8
    elif 8 <= duration < 12 or 60 < duration <= 75:
        fit = 0.6
    else:
        fit = 0.45

    # 3) Pacing: ~2,2-4,8 kata/detik terasa padat tapi tidak dikejar.
    if 2.2 <= wps <= 4.8:
        pace = 1.0
    elif 1.5 <= wps < 2.2 or 4.8 < wps <= 6.0:
        pace = 0.75
    elif wps > 6.0:
        pace = 0.6
    elif wps > 0:
        pace = 0.5
    else:
        pace = 0.35

    # 4) Emosi / kata pemicu + sapaan orang kedua.
    hits = sum(1 for w in words if w in POWER_WORDS)
    emotion = 0.25 + min(0.45, hits * 0.09)
    if any(w in CTA_WORDS for w in words):
        emotion += 0.1
    if "!" in (transcript or ""):
        emotion += 0.08
    if any(w in lower for w in SECOND_PERSON):
        emotion += 0.12

    # 5) Kejelasan: subtitle/caption menaikkan watch-time (ditonton tanpa suara).
    clarity = 0.35 + (0.4 if has_subtitle else 0.0) + (0.25 if has_caption else 0.0)

    hook, fit, pace, emotion, clarity = (
        _ratio(hook), _ratio(fit), _ratio(pace), _ratio(emotion), _ratio(clarity)
    )
    raw = (
        hook * 0.30 + fit * 0.20 + pace * 0.20 + emotion * 0.20 + clarity * 0.10
    )
    score = round(max(28.0, min(97.0, raw * 100.0)), 1)

    factors: Dict[str, Any] = {
        "hook": hook,
        "duration": fit,
        "pacing": pace,
        "emotion": emotion,
        "clarity": clarity,
        "label": _label(score),
        "signals": {
            "words": count,
            "words_per_sec": round(wps, 2),
            "power_words": hits,
            "duration_sec": round(duration, 1),
        },
    }
    if estimated:
        factors["estimated"] = True

    best = max(
        (("hook", hook), ("durasi", fit), ("pacing", pace), ("emosi", emotion), ("kejelasan", clarity)),
        key=lambda item: item[1],
    )
    notes = [f"Kekuatan utama: {best[0]} ({int(best[1] * 100)}%)."]
    if not has_subtitle:
        notes.append("Belum ada subtitle — watch-time tanpa suara bisa turun.")
    if fit <= 0.6:
        notes.append("Durasi di luar rentang ideal 18–45 detik.")
    factors["reasoning"] = " ".join(notes)

    return {"score": score, "factors": factors}
