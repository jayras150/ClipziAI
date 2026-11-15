"""Unit test jalur crop auto zoom (tanpa ffmpeg/OpenCV)."""
import asyncio
import re
from pathlib import Path
from typing import Any

import pytest

from app.services.processor import (
    VideoProcessor,
    _FaceDetection,
    _FaceTrack,
    _SpeakerCropPlan,
    _SubjectState,
)


def _primary_id(
    processor: VideoProcessor,
    active: dict[int, _FaceTrack],
    all_tracks: dict[int, _FaceTrack],
    state: _SubjectState,
) -> int:
    primary = processor._choose_primary(active, all_tracks, state, 0.0, 640, 360)
    assert primary is not None
    return primary.track_id


def test_interpolates_samples_to_every_output_frame():
    track = [
        (0.0, 100.0, 200.0, 608.0, 1080.0),
        (0.4, 160.0, 240.0, 608.0, 1080.0),
    ]

    dense = VideoProcessor._interpolate_track_frames(track, duration=1.0, output_fps=30)

    assert len(dense) == 30
    assert dense[0] == (0.0, 100.0, 200.0, 608.0, 1080.0)
    assert dense[12][0] == pytest.approx(0.4)
    assert dense[12][1] == 160.0
    assert dense[12][2] == 240.0
    assert dense[-1][0] == pytest.approx(29 / 30)


def test_interpolation_does_not_force_even_x_y():
    track = [
        (0.0, 101.0, 51.0, 608.0, 1080.0),
        (0.2, 103.0, 53.0, 608.0, 1080.0),
    ]

    dense = VideoProcessor._interpolate_track_frames(track, duration=0.3, output_fps=30)
    xs = {int(item[1]) for item in dense}
    ys = {int(item[2]) for item in dense}

    # x/y ganjil harus tetap mungkin; hanya w/h yang wajib genap.
    assert any(value % 2 for value in xs)
    assert any(value % 2 for value in ys)


def test_single_sample_is_held_for_whole_clip():
    dense = VideoProcessor._interpolate_track_frames(
        [(0.0, 120.0, 220.0, 608.0, 1080.0)],
        duration=1.0,
        output_fps=30,
    )

    assert len(dense) == 30
    assert all(item[1:] == (120.0, 220.0, 608.0, 1080.0) for item in dense)


def test_empty_track_and_zero_duration():
    assert VideoProcessor._interpolate_track_frames([], duration=1.0, output_fps=30) == []

    dense = VideoProcessor._interpolate_track_frames(
        [(0.0, 10.0, 20.0, 608.0, 1080.0)],
        duration=0.0,
        output_fps=30,
    )
    assert len(dense) == 1


def test_duplicate_sample_times_are_deduplicated():
    dense = VideoProcessor._interpolate_track_frames(
        [
            (0.0, 10.0, 20.0, 608.0, 1080.0),
            (0.0, 30.0, 40.0, 608.0, 1080.0),
        ],
        duration=0.2,
        output_fps=30,
    )

    assert dense[0][1] == 30.0
    assert dense[0][2] == 40.0


def test_render_writes_one_sendcmd_per_output_frame(monkeypatch, tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    plan = _SpeakerCropPlan(
        primary=[
            (0.0, 100.0, 200.0, 608.0, 1080.0),
            (1.0, 200.0, 300.0, 608.0, 1080.0),
        ]
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        processor,
        "_speaker_track_sync",
        lambda *args, **kwargs: plan,
    )

    def fake_run_ffmpeg(cmd):
        captured["cmd"] = cmd
        chain = cmd[cmd.index("-vf") + 1]
        match = re.search(r"sendcmd=f='([^']+)'", chain)
        assert match is not None
        # `_escape_filter_path` meng-escape ":" untuk filtergraph ffmpeg.
        cmd_path = match.group(1).replace(r"\:", ":")
        captured["commands"] = Path(cmd_path).read_text(encoding="utf-8").splitlines()

    monkeypatch.setattr(processor, "_run_ffmpeg", fake_run_ffmpeg)

    output = tmp_path / "auto-zoom.mp4"
    asyncio.run(
        processor.track_speaker_crop(
            "input.mp4",
            str(output),
            duration=1.0,
            aspect_ratio="9:16",
            zoom=1.0,
        )
    )

    chain = captured["cmd"][captured["cmd"].index("-vf") + 1]
    assert chain.startswith("fps=30,setpts=PTS-STARTPTS,sendcmd=")

    commands = captured["commands"]
    assert len(commands) == 60  # 30 frame x 2 command (x dan y)
    assert commands[0].startswith("0.000 crop x 100;")
    assert commands[1].startswith("0.000 crop y 200;")
    assert commands[-2].startswith("0.967 crop x ")
    assert commands[-1].startswith("0.967 crop y ")


def test_face_tracker_keeps_stable_id_across_frames(tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    active = {}
    all_tracks = {}
    next_id = 1

    for index, x in enumerate((100.0, 102.0, 104.0, 106.0)):
        detections = [_FaceDetection(x=x, y=100.0, w=50.0, h=50.0, score=0.9)]
        active, next_id = processor._update_face_tracks(
            active,
            all_tracks,
            detections,
            now=index / 8.0,
            next_id=next_id,
        )

    assert len(all_tracks) == 1
    track = next(iter(all_tracks.values()))
    assert track.track_id == 1
    assert track.hits == 4
    assert len(track.observations) == 4


def test_primary_switch_needs_hysteresis(monkeypatch, tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    first = _FaceTrack(1, 280.0, 100.0, 50.0, 50.0, 0.8, hits=10)
    second = _FaceTrack(2, 100.0, 100.0, 50.0, 50.0, 0.8, hits=10)
    active = {1: first, 2: second}
    all_tracks = {1: first, 2: second}
    state = _SubjectState(primary_id=1, last_primary_seen=0.0)

    # Subjek kedua sedikit lebih kuat: belum boleh switch.
    monkeypatch.setattr(
        processor,
        "_track_strength",
        lambda track, src_w, src_h: 10.0 if track.track_id == 1 else 11.0,
    )
    for _ in range(6):
        assert _primary_id(processor, active, all_tracks, state) == 1

    # Baru setelah challenger jauh lebih kuat dan stabil, switch.
    monkeypatch.setattr(
        processor,
        "_track_strength",
        lambda track, src_w, src_h: 10.0 if track.track_id == 1 else 20.0,
    )
    for _ in range(4):
        assert _primary_id(processor, active, all_tracks, state) == 1
    assert _primary_id(processor, active, all_tracks, state) == 2


def test_split_pair_requires_far_apart_faces(tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    first = _FaceTrack(1, 50.0, 100.0, 50.0, 50.0, 0.8, hits=5)
    far = _FaceTrack(2, 450.0, 100.0, 50.0, 50.0, 0.8, hits=5)
    near = _FaceTrack(3, 80.0, 100.0, 50.0, 50.0, 0.8, hits=5)

    assert processor._choose_split_pair({1: first, 2: far}, first, 640, 360) == (1, 2)
    assert processor._choose_split_pair({1: first, 3: near}, first, 640, 360) is None


def test_track_samples_fall_back_to_center_after_face_lost(tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    track = _FaceTrack(
        1,
        300.0,
        150.0,
        40.0,
        40.0,
        0.9,
        last_seen=1.0,
        observations=[(1.0, 320.0, 170.0, 40.0, 40.0, 0.9)],
    )
    samples = processor._track_samples(track, 3.0, 640, 360, 200.0, 300.0)

    assert samples[0][0] == 0.0  # mulai dari tengah sebelum wajah muncul
    assert samples[-1][0] == pytest.approx(2.0)
    assert samples[-1][1] == pytest.approx(220.0)  # center x


def test_stabilizer_limits_step_and_holds_deadzone():
    track = [
        (index / 30, 100.0 if index < 10 else 200.0, 100.0, 608.0, 1080.0)
        for index in range(40)
    ]
    stable = VideoProcessor._stabilize_track_frames(track, window=5)
    deltas = [abs(stable[i][1] - stable[i - 1][1]) for i in range(1, len(stable))]

    assert max(deltas) <= 5.0
    assert stable[0][1] == 100.0
    assert stable[-1][1] > 100.0


def test_split_render_uses_two_crop_targets_and_vstack(monkeypatch, tmp_path):
    processor = VideoProcessor(work_dir=str(tmp_path))
    plan = _SpeakerCropPlan(
        primary=[
            (0.0, 100.0, 200.0, 608.0, 540.0),
            (1.0, 200.0, 200.0, 608.0, 540.0),
        ],
        secondary=[
            (0.0, 500.0, 200.0, 608.0, 540.0),
            (1.0, 600.0, 200.0, 608.0, 540.0),
        ],
        split=True,
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        processor,
        "_speaker_track_sync",
        lambda *args, **kwargs: plan,
    )

    def fake_run_ffmpeg(cmd):
        captured["cmd"] = cmd
        graph = cmd[cmd.index("-filter_complex") + 1]
        paths = re.findall(r"sendcmd=f='([^']+)'", graph)
        assert len(paths) == 2
        captured["commands"] = [
            Path(path.replace(r"\:", ":")).read_text(encoding="utf-8").splitlines()
            for path in paths
        ]

    monkeypatch.setattr(processor, "_run_ffmpeg", fake_run_ffmpeg)

    output = tmp_path / "split.mp4"
    asyncio.run(
        processor.track_speaker_crop(
            "input.mp4",
            str(output),
            duration=1.0,
            aspect_ratio="9:16",
            zoom=1.0,
        )
    )

    graph = captured["cmd"][captured["cmd"].index("-filter_complex") + 1]
    assert "crop@top" in graph
    assert "crop@bottom" in graph
    assert "vstack=inputs=2" in graph
    assert captured["cmd"][captured["cmd"].index("-map") + 1] == "[v]"

    top_commands, bottom_commands = captured["commands"]
    assert len(top_commands) == 60
    assert len(bottom_commands) == 60
    assert top_commands[1].startswith("0.000 crop@top y ")
    assert bottom_commands[1].startswith("0.000 crop@bottom y ")
