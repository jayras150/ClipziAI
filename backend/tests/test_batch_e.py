"""Batch E: upload presign, multi-segment, caption, Ken Burns, karaoke."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.uploads import MAX_UPLOAD_BYTES, validate_upload_request
from app.services.caption_ass import apply_caption_overrides, build_ass
from app.services.pipeline import _build_segment_timeline, _normalise_segments, _slice_segments
from app.services.processor import VideoProcessor


def test_validate_upload_request_accepts_video_and_returns_safe_suffix():
    suffix = validate_upload_request(
        filename="Talk Final.MOV",
        content_type="video/quicktime",
        size=10_000,
        duration_seconds=120,
    )
    assert suffix == "mov"


def test_validate_upload_request_rejects_bad_type_and_oversize():
    with pytest.raises(HTTPException) as bad_type:
        validate_upload_request(filename="a.txt", content_type="text/plain", size=10)
    assert bad_type.value.status_code == 400

    with pytest.raises(HTTPException) as too_big:
        validate_upload_request(
            filename="a.mp4",
            content_type="video/mp4",
            size=MAX_UPLOAD_BYTES + 1,
        )
    assert too_big.value.status_code == 413


def test_normalise_segments_drops_invalid_and_keeps_order():
    segments = _normalise_segments(
        [
            {"start": 30, "end": 35, "mute": True},
            {"start": "bad", "end": 5},
            {"start": 10, "end": 8},
            {"start": 5, "end": 12},
        ]
    )
    assert segments == [
        {"start": 30.0, "end": 35.0, "mute": True},
        {"start": 5.0, "end": 12.0, "mute": False},
    ]


def test_slice_segments_also_shifts_word_timestamps():
    transcript = [
        {
            "start": 10,
            "end": 20,
            "text": "halo dunia",
            "words": [
                {"word": "halo", "start": 10, "end": 12},
                {"word": "dunia", "start": 18, "end": 20},
            ],
        }
    ]
    sliced = _slice_segments(transcript, 10, 15)
    assert sliced[0]["start"] == 0
    assert sliced[0]["words"][0]["start"] == 0
    assert sliced[0]["words"][0]["end"] == 2


def test_build_segment_timeline_offsets_words_for_concat():
    transcript = [
        {"start": 10, "end": 15, "text": "satu", "words": [{"word": "satu", "start": 10, "end": 12}]},
        {"start": 30, "end": 35, "text": "dua", "words": [{"word": "dua", "start": 30, "end": 32}]},
    ]
    timeline = _build_segment_timeline(
        transcript,
        [
            {"start": 10, "end": 15, "mute": False},
            {"start": 30, "end": 35, "mute": True},
        ],
    )
    assert timeline[0]["words"][0]["start"] == 0
    assert timeline[1]["start"] == 5
    assert timeline[1]["words"][0]["start"] == 5


def test_ken_burns_filter_uses_zoompan_and_direction():
    chain = VideoProcessor.ken_burns_filter_chain(
        1080, 1920, duration=10, output_fps=30, zoom=1.2, direction="right-left"
    )
    assert "zoompan=" in chain
    assert "1-on/300" in chain
    assert "s=1080x1920" in chain


def test_caption_overrides_convert_color_size_and_font():
    style = apply_caption_overrides(
        {},
        height=1920,
        caption_color="#FF0000",
        caption_size=96,
        caption_font="serif",
    )
    assert style["PrimaryColour"] == "&H000000FF"
    assert float(style["FontSize"]) == pytest.approx(14.4)
    assert style["FontName"] == "DejaVu Serif"


def test_karaoke_off_uses_primary_colour_for_active_word(tmp_path):
    segments = [
        {
            "start": 0,
            "end": 2,
            "text": "halo dunia",
            "words": [
                {"word": "halo", "start": 0, "end": 1},
                {"word": "dunia", "start": 1, "end": 2},
            ],
        }
    ]
    output = tmp_path / "caption.ass"
    built = build_ass(
        segments,
        str(output),
        "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF",
        1080,
        1920,
        clip_start=0,
        clip_end=2,
        karaoke=False,
    )
    assert built == str(output)
    body = output.read_text(encoding="utf-8")
    assert "\\c&H00FFFFFF" in body
