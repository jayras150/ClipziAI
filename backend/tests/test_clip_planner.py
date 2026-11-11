"""Unit test clip planner + speech boundaries (tanpa ffmpeg/DB)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.services.clip_planner import plan_clip_quota, plan_clips, score_candidate
from app.services.speech_boundaries import (
    SpeechMap,
    build_sentences,
    extract_words,
)


def _make_segments(
    sentences: int = 80,
    words_per: int = 12,
    wps: float = 2.6,
    gap: float = 0.6,
    hook_sentences: Tuple[int, ...] = (),
) -> Tuple[List[Dict[str, Any]], float]:
    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    for index in range(sentences):
        words: List[Dict[str, Any]] = []
        for word_index in range(words_per):
            duration = 1.0 / wps
            text = f"kata{index}x{word_index}"
            if index in hook_sentences and word_index == 0:
                text = "Rahasia"
            if word_index == words_per - 1:
                text += "?" if index in hook_sentences else "."
            words.append(
                {
                    "word": text,
                    "start": round(cursor, 3),
                    "end": round(cursor + duration, 3),
                    "probability": 0.9,
                }
            )
            cursor += duration
        segments.append(
            {
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "text": " ".join(word["word"] for word in words),
                "words": words,
            }
        )
        cursor += gap
    return segments, cursor


def _build_map(segments: List[Dict[str, Any]], total: float) -> SpeechMap:
    words = extract_words(segments)
    sentences = build_sentences(words)
    return SpeechMap(words, sentences, [], total)


def test_quota_mengikuti_panjang_video():
    assert plan_clip_quota(5 * 60) == 3
    assert plan_clip_quota(15 * 60) == 3
    assert plan_clip_quota(30 * 60) == 6
    assert plan_clip_quota(60 * 60) == 8
    assert plan_clip_quota(120 * 60) == 10
    assert plan_clip_quota(300 * 60) == 10
    # interpolasi linear antar titik
    assert plan_clip_quota(45 * 60) == 7
    assert plan_clip_quota(90 * 60) == 9


def test_planner_memotong_di_batas_kalimat_dan_tidak_overlap():
    segments, total = _make_segments()
    clips = plan_clips(segments, [], total, 60, 90, quota=3)

    assert clips, "planner harus menghasilkan klip"
    assert len(clips) <= 3

    speech = _build_map(segments, total)
    previous_end = -1.0
    for clip in clips:
        start, end = clip["start"], clip["end"]
        assert start >= 0
        assert end <= total + 0.01
        # tidak overlap dengan klip sebelumnya
        assert start > previous_end
        previous_end = end
        # durasi tidak kaku: di dalam jendela soft
        assert 55.0 <= clip["duration"] <= 113.0
        # batas tidak memotong kata
        ok, notes = speech.validate(start, end)
        assert ok, notes
        # klip mulai sedikit sebelum kata pertama (pre-roll), bukan sesudahnya
        first = speech.next_word(start, tolerance=0.0)
        assert first is not None
        assert first.start - start <= 0.45


def test_planner_menyebar_klip_di_seluruh_timeline():
    segments, total = _make_segments()
    clips = plan_clips(segments, [], total, 60, 90, quota=3)
    buckets = {int(clip["start"] / total * 3) for clip in clips}
    assert len(buckets) >= 2, "klip tidak boleh menumpuk di awal video"


def test_planner_melewati_kalimat_pembuka_gumaman():
    segments, total = _make_segments()
    segments[0]["words"][0]["word"] = "eee"
    clips = plan_clips(segments, [], total, 60, 90, quota=3)
    assert clips
    assert min(clip["start"] for clip in clips) > 0.0


def test_hook_meningkatkan_skor_kandidat():
    plain_segments, plain_total = _make_segments(sentences=40)
    hook_segments, hook_total = _make_segments(sentences=40, hook_sentences=(20,))

    plain_map = _build_map(plain_segments, plain_total)
    hook_map = _build_map(hook_segments, hook_total)

    # Jendela sama panjang (12 kalimat) supaya perbandingan adil.
    plain = score_candidate(
        plain_map,
        plain_map.refine_start(plain_map.sentences[20].start),
        plain_map.refine_end(plain_map.sentences[31].end),
        60,
        90,
    )
    hook = score_candidate(
        hook_map,
        hook_map.refine_start(hook_map.sentences[20].start),
        hook_map.refine_end(hook_map.sentences[31].end),
        60,
        90,
    )
    assert hook["score"] > plain["score"]
    assert hook["factors"]["hook_bonus"] > plain["factors"]["hook_bonus"]


def test_transkrip_kosong_tidak_melempar_exception():
    assert plan_clips([], [], 600.0, 60, 90, quota=3) == []
