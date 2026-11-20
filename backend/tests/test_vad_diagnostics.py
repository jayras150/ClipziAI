"""Regresi investigasi VAD: diagnostik audio, fallback parsial, pemilihan stream.

Latar belakang (terukur):
  - VAD faster-whisper 1.2.1 mendeteksi 100% speech pada audio normal, termasuk
    MP3 16 kHz mono, gain -30 dB, noise 0 dB SNR, dan audio 10:34.
  - Kegagalan total hanya terjadi pada audio tanpa speech / nol amplitudo.
  - Pipeline lama hanya fallback bila 0 segmen; VAD yang menyisakan <5% audio
    tidak dilaporkan.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class _Segment:
    id = 0
    start = 0.0
    end = 1.0
    text = " halo"
    words = []


class _FakeModel:
    """Model palsu: perilaku VAD ditentukan oleh `vad_segments`/`kept`."""

    def __init__(self, vad_segments: int = 1, kept: float = 90.0) -> None:
        self.vad_segments = vad_segments
        self.kept = kept
        self.calls: list[bool] = []

    def transcribe(self, audio_path, **kwargs):
        vad = bool(kwargs.get("vad_filter"))
        self.calls.append(vad)
        if vad:
            segments = [_Segment() for _ in range(self.vad_segments)]
            duration_after_vad = self.kept
        else:
            segments = [_Segment()]
            duration_after_vad = 100.0
        return iter(segments), SimpleNamespace(
            language="id",
            duration=100.0,
            duration_after_vad=duration_after_vad,
        )


def _run(monkeypatch, model, env: dict | None = None):
    import app.services.transcriber as mod

    monkeypatch.setattr(mod, "_probe_audio_summary", lambda path: {})
    monkeypatch.setattr(
        mod,
        "_decode_audio_for_stats",
        lambda path: (None, {"rms": 0.01, "peak": 0.05, "rms_dbfs": -40.0}),
    )
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    transcriber = mod.AudioTranscriber()
    return transcriber._transcribe_sync(model, "audio.mp3", None)


def test_vad_retry_saat_hanya_2_persen_audio_dipertahankan(monkeypatch):
    model = _FakeModel(vad_segments=1, kept=2.0)

    segments, _info, vad_meta = _run(monkeypatch, model)

    assert model.calls == [True, False], "VAD menyisakan 2% → harus retry tanpa VAD"
    assert len(segments) == 1
    assert vad_meta["fallback"] is True
    assert vad_meta["speech_ratio"] == 0.02
    assert vad_meta["signal"]["rms"] == 0.01


def test_vad_tidak_retry_saat_speech_wajar(monkeypatch):
    model = _FakeModel(vad_segments=2, kept=90.0)

    segments, _info, vad_meta = _run(monkeypatch, model)

    assert model.calls == [True], "speech 90% tidak boleh memicu transkripsi ulang"
    assert len(segments) == 2
    assert vad_meta["fallback"] is False


def test_vad_mode_on_tidak_retry_meski_kosong(monkeypatch):
    model = _FakeModel(vad_segments=0, kept=0.0)

    segments, _info, vad_meta = _run(monkeypatch, model, env={"WHISPER_VAD": "on"})

    assert model.calls == [True], "WHISPER_VAD=on = tanpa retry (sesuai kontrak)"
    assert segments == []
    assert vad_meta["fallback"] is False


def test_ambang_min_keep_bisa_diatur_env(monkeypatch):
    from app.services.transcriber import DEFAULT_VAD_MIN_KEEP, _vad_min_keep

    monkeypatch.delenv("WHISPER_VAD_MIN_KEEP", raising=False)
    assert _vad_min_keep() == DEFAULT_VAD_MIN_KEEP

    monkeypatch.setenv("WHISPER_VAD_MIN_KEEP", "0.25")
    assert _vad_min_keep() == 0.25

    monkeypatch.setenv("WHISPER_VAD_MIN_KEEP", "bukan-angka")
    assert _vad_min_keep() == DEFAULT_VAD_MIN_KEEP

    monkeypatch.setenv("WHISPER_VAD_MIN_KEEP", "9")
    assert _vad_min_keep() == 1.0


def test_audio_signal_stats_menghitung_rms_dan_peak():
    import numpy as np

    from app.services.transcriber import audio_signal_stats

    stats = audio_signal_stats(np.array([0.0, 0.5, -0.5], dtype=np.float32))

    assert stats["samples"] == 3
    assert stats["peak"] == 0.5
    assert abs(stats["rms"] - 0.5 * (2 / 3) ** 0.5) < 1e-4
    assert stats["peak_dbfs"] < 0

    empty = audio_signal_stats(np.array([], dtype=np.float32))
    assert empty["samples"] == 0
    assert empty["rms_dbfs"] == -120.0


def test_pemilihan_audio_stream_memprioritaskan_default():
    from app.services.processor import VideoProcessor

    streams = [
        {"index": 1, "disposition": {"default": 0}},
        {"index": 3, "disposition": {"default": 1}},
    ]

    assert VideoProcessor.choose_audio_stream(streams) == 3
    assert VideoProcessor.choose_audio_stream([{"index": 2}]) == 2
    assert VideoProcessor.choose_audio_stream([]) is None


def test_kandidat_stream_audio_default_lalu_bitrate():
    from app.services.processor import VideoProcessor

    streams = [
        {"index": 1, "bit_rate": "500", "disposition": {"default": 0}},
        {"index": 2, "bit_rate": "56000", "disposition": {"default": 1}},
        {"index": 3, "bit_rate": "128000", "disposition": {"default": 0}},
    ]

    assert VideoProcessor.audio_stream_candidates(streams) == [2, 3, 1]
    assert VideoProcessor.audio_stream_candidates([]) == []


def test_ambang_senyap_bisa_diatur_env(monkeypatch):
    from app.services.processor import DEFAULT_AUDIO_SILENCE_RMS, VideoProcessor

    monkeypatch.delenv("AUDIO_SILENCE_RMS", raising=False)
    assert VideoProcessor._audio_silence_threshold() == DEFAULT_AUDIO_SILENCE_RMS

    monkeypatch.setenv("AUDIO_SILENCE_RMS", "0.01")
    assert VideoProcessor._audio_silence_threshold() == 0.01

    monkeypatch.setenv("AUDIO_SILENCE_RMS", "bukan-angka")
    assert VideoProcessor._audio_silence_threshold() == DEFAULT_AUDIO_SILENCE_RMS

    monkeypatch.setenv("AUDIO_SILENCE_RMS", "9")
    assert VideoProcessor._audio_silence_threshold() == 1.0


def test_perintah_ekstraksi_audio_memakai_map_eksplisit():
    from app.services.processor import VideoProcessor

    cmd = VideoProcessor._build_audio_extract_cmd("in.mp4", "out.mp3", 16000, 3)
    assert cmd[cmd.index("-map") + 1] == "0:3"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert "-vn" in cmd

    legacy = VideoProcessor._build_audio_extract_cmd("in.mp4", "out.mp3")
    assert "-map" not in legacy, "tanpa stream_index harus tetap kompatibel"


def _requirements_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (BACKEND_ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("av")
    ]


def test_semua_requirements_whisper_mem_pin_av_di_bawah_19():
    """av 19 menghapus metadata_errors → faster-whisper 1.2.x gagal decode."""
    for name in (
        "requirements-whisper-cpu.txt",
        "requirements-whisper-local.txt",
        "requirements-gpu-whisper.txt",
    ):
        lines = _requirements_lines(name)
        assert lines, f"{name} harus memuat pin av eksplisit"
        assert any("<19" in line for line in lines), (name, lines)


def _load_check_media_deps():
    path = BACKEND_ROOT / "deployments" / "check_media_deps.py"
    spec = importlib.util.spec_from_file_location("check_media_deps", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_check_media_deps_mendeteksi_av_lama_dan_av_19():
    module = _load_check_media_deps()

    class _Av18:
        __version__ = "18.1.0"

        @staticmethod
        def open(file, mode=None, metadata_errors=None):
            return None

    class _Av19:
        __version__ = "19.0.2"

        @staticmethod
        def open(file, mode=None):
            return None

    assert module.pyav_supports_metadata_errors(_Av18) is True
    assert module.pyav_supports_metadata_errors(_Av19) is False
