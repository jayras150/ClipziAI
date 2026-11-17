"""Tes pre-flight format video + klasifikasi error JS challenge YouTube."""
from app.services import downloader as dl
from app.services.download_errors import (
    CATEGORY_FORMAT_UNAVAILABLE,
    classify_download_error,
)


def test_klasifikasi_js_challenge():
    assert (
        classify_download_error("Signature extraction failed: Some formats may be missing")
        == CATEGORY_FORMAT_UNAVAILABLE
    )
    assert (
        classify_download_error("Only images are available for download. use --list-formats")
        == CATEGORY_FORMAT_UNAVAILABLE
    )
    assert (
        classify_download_error("ERROR: [youtube] x: Requested format is not available")
        == CATEGORY_FORMAT_UNAVAILABLE
    )


def test_deteksi_runtime_js_dan_ejs():
    assert isinstance(dl._ejs_available(), bool)
    assert isinstance(dl._js_runtime(), str)


def test_preflight_dilewati_untuk_non_youtube():
    downloader = dl.VideoDownloader(".")
    assert downloader._preflight_formats("https://www.tiktok.com/@x/video/1", {}) == (
        1,
        0,
        "dilewati (bukan YouTube)",
    )


def test_preflight_storyboard_only(monkeypatch):
    downloader = dl.VideoDownloader(".")
    storyboard = [
        {"format_id": "sb0", "vcodec": "none", "acodec": "none"},
        {"format_id": "sb1", "vcodec": "none", "acodec": "none"},
    ]
    monkeypatch.setattr(
        dl.VideoDownloader,
        "_probe_formats_sync",
        lambda self, url, opts: ({}, storyboard),
    )
    videos, total, note = downloader._preflight_formats(
        "https://www.youtube.com/watch?v=abc123xyz", {}
    )
    assert (videos, total) == (0, 2)
    assert "storyboard-only" in note


def test_preflight_menemukan_video(monkeypatch):
    downloader = dl.VideoDownloader(".")
    formats = [
        {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a", "height": 360},
        {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080},
        {"format_id": "sb0", "vcodec": "none", "acodec": "none"},
    ]
    monkeypatch.setattr(
        dl.VideoDownloader,
        "_probe_formats_sync",
        lambda self, url, opts: ({}, formats),
    )
    videos, total, note = downloader._preflight_formats(
        "https://youtu.be/abc123xyz", {}
    )
    assert (videos, total) == (2, 3)
    assert note == ""
