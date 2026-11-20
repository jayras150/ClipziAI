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
        from types import SimpleNamespace

        vad = bool(kwargs.get("vad_filter"))
        self.calls.append(vad)
        if vad:
            return iter([]), SimpleNamespace(
                language="id", duration=10.0, duration_after_vad=0.0
            )
        return iter([_Segment()]), SimpleNamespace(
            language="id", duration=10.0, duration_after_vad=10.0
        )


def test_vad_retry_saat_seluruh_audio_dihapus(monkeypatch):
    import app.services.transcriber as mod
    from app.services.transcriber import AudioTranscriber

    monkeypatch.setattr(mod, "_probe_audio_summary", lambda path: {})
    monkeypatch.setattr(
        mod, "_decode_audio_for_stats", lambda path: (None, {"rms": 0.01, "peak": 0.05})
    )
    transcriber = AudioTranscriber()
    model = _FakeModel()

    segments, _info, vad_meta = transcriber._transcribe_sync(model, "audio.mp3", None)

    assert model.calls == [True, False], "harus retry tanpa VAD setelah hasil kosong"
    assert len(segments) == 1
    assert segments[0]["text"].strip() == "halo"
    assert vad_meta["fallback"] is True
    assert vad_meta["segments_with_vad"] == 0
    assert vad_meta["segments_without_vad"] == 1


def test_whisper_vad_off_langsung_tanpa_vad(monkeypatch):
    import app.services.transcriber as mod
    from app.services.transcriber import AudioTranscriber

    monkeypatch.setenv("WHISPER_VAD", "off")
    monkeypatch.setattr(mod, "_probe_audio_summary", lambda path: {})
    transcriber = AudioTranscriber()
    model = _FakeModel()

    segments, _info, vad_meta = transcriber._transcribe_sync(model, "audio.mp3", None)

    assert model.calls == [False], "WHISPER_VAD=off tidak boleh memakai VAD"
    assert len(segments) == 1
    assert vad_meta["enabled"] is False


def test_hwaccel_off_menghasilkan_argumen_kosong(monkeypatch):
    from app.services.processor import VideoProcessor

    monkeypatch.setenv("FFMPEG_HWACCEL", "off")
    VideoProcessor._HWACCEL_CACHE.clear()
    assert VideoProcessor._hwaccel_args() == []
    VideoProcessor._HWACCEL_CACHE.clear()


def _force_scene_methods(monkeypatch, hwaccel):
    from app.services.processor import VideoProcessor

    calls = {"proxy": 0, "native": 0}
    monkeypatch.setattr(
        VideoProcessor, "_hwaccel_args", classmethod(lambda cls: list(hwaccel))
    )
    monkeypatch.setattr(
        VideoProcessor,
        "_detect_scenes_proxy",
        lambda self, path: (
            calls.__setitem__("proxy", calls["proxy"] + 1)
            or [{"start": 0.0, "end": 5.0, "confidence": 1.0}]
        ),
    )
    monkeypatch.setattr(
        VideoProcessor,
        "_detect_scenes_native",
        lambda self, path: (
            calls.__setitem__("native", calls["native"] + 1) or []
        ),
    )
    return calls


def test_auto_memakai_proxy_saat_nvdec_tersedia(monkeypatch):
    from app.services.processor import VideoProcessor

    monkeypatch.delenv("SCENE_DETECT_MODE", raising=False)
    monkeypatch.delenv("FFMPEG_HWACCEL", raising=False)
    calls = _force_scene_methods(monkeypatch, ["-hwaccel", "cuda"])

    VideoProcessor()._detect_scenes_sync("x.mp4")

    assert calls == {"proxy": 1, "native": 0}


def test_auto_tanpa_nvdec_memakai_pyscenedetect(monkeypatch):
    from app.services.processor import VideoProcessor

    monkeypatch.delenv("SCENE_DETECT_MODE", raising=False)
    calls = _force_scene_methods(monkeypatch, [])

    VideoProcessor()._detect_scenes_sync("x.mp4")

    assert calls == {"proxy": 0, "native": 1}, (
        "tanpa NVDEC, proxy terbukti lebih lambat → langsung PySceneDetect"
    )


def test_storage_isolated_memakai_engine_sendiri():
    import inspect

    from app.services import storage_registry as registry

    source = inspect.getsource(registry._load_storage_config_isolated)

    assert "NullPool" in source
    assert "create_async_engine" in source
    assert "engine.dispose" in source

