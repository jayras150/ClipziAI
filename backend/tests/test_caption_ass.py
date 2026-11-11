"""Unit test builder caption ASS (karaoke, ukuran, posisi)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.services.caption_ass import build_ass, group_into_cues
from app.services.speech_boundaries import Word, extract_words


def _segments(words: List[str], wps: float = 3.0, start: float = 10.0) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    cursor = start
    for text in words:
        duration = 1.0 / wps
        items.append(
            {
                "word": text,
                "start": round(cursor, 3),
                "end": round(cursor + duration, 3),
                "probability": 0.9,
            }
        )
        cursor += duration
    return [
        {
            "start": items[0]["start"],
            "end": items[-1]["end"],
            "text": " ".join(words),
            "words": items,
        }
    ]


FORCE_STYLE = (
    "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,Outline=1.6,Shadow=0,Alignment=2,MarginV=22"
)


def test_build_ass_menskalakan_ukuran_dan_margin(tmp_path: Path):
    segments = _segments(["halo", "semua", "kita", "mulai", "sekarang"])
    out = tmp_path / "clip.ass"
    built = build_ass(segments, str(out), FORCE_STYLE, 1080, 1920, clip_start=10.0, clip_end=14.0)

    assert built == str(out)
    content = out.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    # FontSize 16 (basis 288) -> 107 px di 1920
    assert "Cap,DejaVu Sans,107," in content
    # MarginV 22 (basis 288) -> 147 px, jauh di atas UI YouTube
    assert ",60,60,147,1" in content


def test_kata_dikelompokkan_maks_lima_per_cue():
    words = extract_words(_segments([f"kata{i}" for i in range(12)]))
    cues = group_into_cues(words, max_words=5, max_chars=26)
    assert all(len(cue) <= 5 for cue in cues)
    assert sum(len(cue) for cue in cues) == 12


def test_setiap_kata_punya_event_highlight(tmp_path: Path):
    words = ["ini", "contoh", "kalimat", "pendek"]
    segments = _segments(words)
    out = tmp_path / "clip.ass"
    build_ass(segments, str(out), FORCE_STYLE, 1080, 1920, clip_start=10.0, clip_end=12.5)

    events = [line for line in out.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
    assert len(events) == len(words)
    for word in words:
        assert f"&H006BC7F4" in "".join(events)
        assert any(word in event for event in events)


def test_clip_start_menggeser_waktu_ke_nol(tmp_path: Path):
    segments = _segments(["satu", "dua", "tiga"], start=60.0)
    out = tmp_path / "clip.ass"
    build_ass(segments, str(out), FORCE_STYLE, 1080, 1920, clip_start=60.0, clip_end=61.2)
    content = out.read_text(encoding="utf-8")
    assert "0:00:00.00" in content


def test_tanpa_kata_tidak_membuat_file(tmp_path: Path):
    out = tmp_path / "clip.ass"
    assert build_ass([], str(out), FORCE_STYLE, 1080, 1920) is None
    assert not out.exists()
