"""Tes validasi berkas klip sebelum upload YouTube (tanpa network)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import youtube


def test_terima_206_video(monkeypatch):
    monkeypatch.setattr(youtube, "_probe_media", lambda url: (206, "video/mp4", 16_595_747))
    youtube._check_video_source("https://files.example/clip.mp4")


def test_terima_octet_stream(monkeypatch):
    monkeypatch.setattr(
        youtube, "_probe_media", lambda url: (200, "application/octet-stream", 1_621_668_947)
    )
    youtube._check_video_source("https://files.example/model.bin")


def test_403_lalu_coba_url_segar(monkeypatch):
    calls: list[str] = []

    def probe(url: str):
        calls.append(url)
        if len(calls) == 1:
            return (403, "text/plain", 0)
        return (206, "video/mp4", 10_000_000)

    monkeypatch.setattr(youtube, "_probe_media", probe)
    monkeypatch.setattr(youtube, "_fresh_storage_url", lambda url: "https://fresh/clip.mp4")
    youtube._check_video_source("https://old/clip.mp4")
    assert calls == ["https://old/clip.mp4", "https://fresh/clip.mp4"]


def test_tolak_html(monkeypatch):
    monkeypatch.setattr(youtube, "_probe_media", lambda url: (200, "text/html", 5000))
    with pytest.raises(HTTPException) as info:
        youtube._check_video_source("https://files.example/clip.mp4")
    assert info.value.status_code == 400
    assert "not a valid video" in str(info.value.detail)


def test_tolak_terlalu_kecil(monkeypatch):
    monkeypatch.setattr(youtube, "_probe_media", lambda url: (200, "video/mp4", 512))
    with pytest.raises(HTTPException):
        youtube._check_video_source("https://files.example/clip.mp4")
