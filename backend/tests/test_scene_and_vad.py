"""Regresi: batas durasi scene detection & retry VAD.

Terukur di Vast: PySceneDetect 0.7 memakai 94s untuk video 1080p 10 menit
(≈9 menit untuk 1 jam). Karena itu:
  - video > SCENE_DETECT_MAX_MINUTES dilewati (rentang klip dibagi merata);
  - VAD yang menghapus SELURUH audio tidak boleh membuat transkrip kosong —
    transkripsi diulang sekali tanpa VAD.
"""
from __future__ import annotations

import asyncio


def _processor():
    from app.services.processor import VideoProcessor

    return VideoProcessor()


def test_scene_detection_dilewati_untuk_video_panjang(monkeypatch):
    processor = _processor()
    monkeypatch.setenv("SCENE_DETECT_MAX_MINUTES", "20")
    monkeypatch.setattr(
        type(processor), "_video_duration_sync", staticmethod(lambda path: 3600.0)
    )
    called = {"n": 0}

    def _fake_sync(self, path):
        called["n"] += 1
        return [{"start": 0.0, "end": 10.0, "confidence": 1.0}]

    monkeypatch.setattr(type(processor), "_detect_scenes_sync", _fake_sync)

    result = asyncio.run(processor.detect_scenes("x.mp4"))

    assert result == [], "video 1 jam tidak boleh menjalankan scene detection"
    assert called["n"] == 0


def test_scene_detection_tetap_jalan_untuk_video_pendek(monkeypatch):
    processor = _processor()
    monkeypatch.setenv("SCENE_DETECT_MAX_MINUTES", "20")
    monkeypatch.setattr(
        type(processor), "_video_duration_sync", staticmethod(lambda path: 300.0)
    )
    called = {"n": 0}

    def _fake_sync(self, path):
        called["n"] += 1
        return [{"start": 0.0, "end": 10.0, "confidence": 1.0}]

    monkeypatch.setattr(type(processor), "_detect_scenes_sync", _fake_sync)

    result = asyncio.run(processor.detect_scenes("x.mp4"))

    assert called["n"] == 1
    assert result and result[0]["end"] == 10.0


class _Word:
    word = "halo"
    start = 0.0
    end = 1.0
    probability = 0.9


class _Segment:
    id = 0
    start = 0.0
    end = 1.0
    text = " halo"
    words = [_Word()]


class _FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio_path, **kwargs):
        vad = bool(kwargs.get("vad_filter"))
        self.calls.append(vad)
        if vad:
            return iter([]), {"language": "id"}
        return iter([_Segment()]), {"language": "id"}


def test_vad_retry_saat_seluruh_audio_dihapus():
    from app.services.transcriber import AudioTranscriber

    transcriber = AudioTranscriber()
    model = _FakeModel()

    segments, _info = transcriber._transcribe_sync(model, "audio.mp3", None)

    assert model.calls == [True, False], "harus retry tanpa VAD setelah hasil kosong"
    assert len(segments) == 1
    assert segments[0]["text"].strip() == "halo"
