"""Unit test AI moment-based reframing (tanpa ffmpeg/OpenCV/GPU)."""
import pytest

from app.services.reframe.config import ReframeConfig, load_reframe_config
from app.services.reframe.detectors import Detection, _nms
from app.services.reframe.features import (
    FrameFeatures,
    composition_score,
    edge_clip_ratio,
    match_face_to_person,
    visibility_ratio,
)
from app.services.reframe.moments import Moment, MomentDetectionEngine
from app.services.reframe.tracker import ByteTrackLite, Track, track_strength
from app.services.reframe.trajectory import build_trajectory, crop_window, smoothstep

SRC_W, SRC_H = 1280, 720


def _det(x, y, w, h, score=0.8):
    return Detection(x, y, w, h, score)


def _features(time, **overrides):
    base = dict(
        time=time,
        person_count=1,
        primary_id=1,
        person_score=0.85,
        face_score=0.9,
        face_ratio=0.002,
        visibility=1.0,
        bbox_area_ratio=0.05,
        motion=0.1,
        activity=0.1,
        composition=0.75,
        stability=1.0,
        bbox=(600.0, 200.0, 80.0, 200.0),
    )
    base.update(overrides)
    return FrameFeatures(**base)


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
def test_config_normalises_weights_to_one():
    config = ReframeConfig(
        weight_confidence=2.0,
        weight_face=1.0,
        weight_visibility=1.0,
        weight_motion=1.0,
        weight_activity=1.0,
        weight_face_size=1.0,
        weight_composition=1.0,
    ).sanitized()

    total = (
        config.weight_confidence
        + config.weight_face
        + config.weight_visibility
        + config.weight_motion
        + config.weight_activity
        + config.weight_face_size
        + config.weight_composition
    )
    assert total == pytest.approx(1.0)


def test_config_clamps_zoom_order():
    config = ReframeConfig(minimum_zoom=1.8, maximum_zoom=1.2).sanitized()
    assert config.maximum_zoom >= config.minimum_zoom


def test_legacy_zoom_level_becomes_maximum_zoom():
    config = load_reframe_config({"zoom_level": 1.8, "auto_zoom": "speaker"})
    assert config.maximum_zoom == pytest.approx(1.8)


def test_zero_weight_config_falls_back_to_defaults():
    config = ReframeConfig(
        weight_confidence=0.0,
        weight_face=0.0,
        weight_visibility=0.0,
        weight_motion=0.0,
        weight_activity=0.0,
        weight_face_size=0.0,
        weight_composition=0.0,
    ).sanitized()
    assert config.weight_confidence > 0


# ----------------------------------------------------------------------
# Detector helpers
# ----------------------------------------------------------------------
def test_nms_removes_overlapping_duplicate():
    boxes = [[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]]
    import numpy as np

    keep = _nms(np.array(boxes, dtype=float), np.array([0.9, 0.8, 0.7]))
    assert keep == [0, 2]


def test_detection_clip_stays_inside_frame():
    det = _det(-20, -10, 100, 100).clipped(1280, 720)
    assert det.x >= 0 and det.y >= 0
    assert det.x + det.w <= 1280


# ----------------------------------------------------------------------
# Tracker
# ----------------------------------------------------------------------
def test_tracker_keeps_id_across_frames():
    tracker = ByteTrackLite(high_threshold=0.3, low_threshold=0.1, min_hits=1)
    ids = []
    for index in range(6):
        tracks = tracker.update([_det(100 + index * 4, 100, 60, 160)], index)
        ids.extend(track.track_id for track in tracks)
    assert set(ids) == {1}


def test_tracker_creates_new_id_after_reset():
    tracker = ByteTrackLite(high_threshold=0.3, low_threshold=0.1, min_hits=1)
    tracker.update([_det(100, 100, 60, 160)], 0)
    tracker.reset()
    tracks = tracker.update([_det(100, 100, 60, 160)], 1)
    assert tracks[0].track_id == 2


def test_track_strength_prefers_stable_centered_subject():
    stable = Track(track_id=1, x=600, y=200, w=80, h=200, score=0.9, hits=12)
    fleeting = Track(track_id=2, x=20, y=20, w=40, h=90, score=0.9, hits=1)
    assert track_strength(stable, SRC_W, SRC_H) > track_strength(fleeting, SRC_W, SRC_H)


# ----------------------------------------------------------------------
# Features
# ----------------------------------------------------------------------
def test_visibility_and_edge_clip():
    assert visibility_ratio((0, 0, 100, 100), 1280, 720) == pytest.approx(1.0)
    assert visibility_ratio((-50, 0, 100, 100), 1280, 720) == pytest.approx(0.5)
    assert edge_clip_ratio((600, 200, 80, 200), 1280, 720) == pytest.approx(0.0)
    assert edge_clip_ratio((-40, 200, 80, 200), 1280, 720) > 0.2


def test_composition_prefers_centered_subject():
    centered = composition_score((600, 200, 80, 200), SRC_W, SRC_H)
    corner = composition_score((10, 5, 80, 200), SRC_W, SRC_H)
    assert centered > corner


def test_face_is_matched_inside_person_head():
    person = (600, 200, 80, 200)
    head = _det(620, 205, 30, 38, 0.9)
    far = _det(100, 500, 30, 38, 0.9)
    assert match_face_to_person(person, [head, far]) is head


# ----------------------------------------------------------------------
# Moment detection
# ----------------------------------------------------------------------
def test_valid_moment_is_selected():
    engine = MomentDetectionEngine(ReframeConfig())
    features = [_features(index / 8.0) for index in range(24)]
    result = engine.detect(features)
    assert len(result.moments) == 1
    assert result.moments[0].duration >= 1.2
    assert result.moments[0].moment_score >= 0.45
    assert result.moments[0].recommended_zoom > 1.0


def test_no_person_produces_no_moment():
    engine = MomentDetectionEngine(ReframeConfig())
    features = [
        _features(index / 8.0, person_count=0, primary_id=None)
        for index in range(24)
    ]
    result = engine.detect(features)
    assert result.moments == []
    assert result.decisions[0].reason == "no_person"


def test_short_blip_is_not_a_moment():
    engine = MomentDetectionEngine(ReframeConfig(minimum_moment_duration=1.2))
    features = [_features(index / 8.0, person_count=0, primary_id=None) for index in range(8)]
    features += [_features((index + 8) / 8.0) for index in range(4)]
    features += [
        _features((index + 12) / 8.0, person_count=0, primary_id=None) for index in range(8)
    ]
    result = engine.detect(features)
    assert result.moments == []


def test_close_up_face_blocks_zoom():
    engine = MomentDetectionEngine(ReframeConfig())
    assert engine._gate(_features(0.0, face_ratio=0.20)) == "face_fills_frame"


def test_invisible_subject_blocks_moment():
    engine = MomentDetectionEngine(ReframeConfig())
    assert engine._gate(_features(0.0, visibility=0.2)) == "subject_not_visible"


def test_zoom_respects_maximum():
    config = ReframeConfig(maximum_zoom=1.6)
    engine = MomentDetectionEngine(config)
    zoom = engine._recommended_zoom(_features(0.0, bbox_area_ratio=0.001))
    assert zoom <= config.sanitized().maximum_zoom + 1e-9


def test_two_moments_are_separated_by_cooldown():
    # Smoothing 0.5s menjembatani celah pendek, jadi celah di sini dibuat
    # cukup panjang (>= 1s) supaya benar-benar terpisah menjadi dua momen.
    config = ReframeConfig(
        minimum_moment_duration=1.0, zoom_cooldown=2.0, smoothing_window=0.5
    )
    engine = MomentDetectionEngine(config)
    features = []
    for index in range(56):
        active = 0 <= index < 12 or 20 <= index < 32
        features.append(
            _features(index / 8.0) if active else _features(
                index / 8.0, person_count=0, primary_id=None
            )
        )
    result = engine.detect(features)
    assert len(result.moments) == 1
    assert result.skip_reasons.get("cooldown", 0) >= 1


def test_moments_far_apart_are_both_kept():
    config = ReframeConfig(minimum_moment_duration=1.0, zoom_cooldown=1.0)
    engine = MomentDetectionEngine(config)
    features = []
    for index in range(80):
        active = 0 <= index < 12 or 48 <= index < 60
        features.append(
            _features(index / 8.0) if active else _features(
                index / 8.0, person_count=0, primary_id=None
            )
        )
    result = engine.detect(features)
    assert len(result.moments) == 2


# ----------------------------------------------------------------------
# Trajectory
# ----------------------------------------------------------------------
def test_crop_window_keeps_target_ratio_and_even_size():
    width, height = crop_window(SRC_W, SRC_H, 9 / 16, 1.0)
    assert width % 2 == 0 and height % 2 == 0
    assert width / height == pytest.approx(9 / 16, abs=0.01)
    assert height == pytest.approx(SRC_H, abs=2)


def test_zoom_reduces_window_size():
    base = crop_window(SRC_W, SRC_H, 9 / 16, 1.0)
    zoomed = crop_window(SRC_W, SRC_H, 9 / 16, 2.0)
    assert zoomed[0] < base[0] and zoomed[1] < base[1]


def test_smoothstep_is_monotonic_and_bounded():
    values = [smoothstep(index / 10.0) for index in range(11)]
    assert values[0] == 0.0 and values[-1] == 1.0
    assert all(a <= b for a, b in zip(values, values[1:]))


def test_trajectory_without_moments_keeps_original_framing():
    config = ReframeConfig()
    trajectory = build_trajectory(
        config=config,
        moments=[],
        samples=[(index / 30.0, 1, 640.0, 360.0) for index in range(60)],
        duration=2.0,
        src_w=SRC_W,
        src_h=SRC_H,
        target_ratio=9 / 16,
        output_fps=30,
    )
    assert len(trajectory.keyframes) == 60
    assert not trajectory.has_zoom
    assert all(frame.phase == "NORMAL" for frame in trajectory.keyframes)


def test_trajectory_zooms_and_returns_to_normal():
    config = ReframeConfig(zoom_in_duration=0.2, zoom_out_duration=0.2, zoom_cooldown=0.2)
    moment = Moment(
        start_time=0.5,
        end_time=1.5,
        confidence=0.9,
        moment_score=0.8,
        target_id=1,
        recommended_zoom=2.0,
    )
    trajectory = build_trajectory(
        config=config,
        moments=[moment],
        samples=[(index / 30.0, 1, 640.0, 360.0) for index in range(60)],
        duration=2.0,
        src_w=SRC_W,
        src_h=SRC_H,
        target_ratio=9 / 16,
        output_fps=30,
    )
    phases = {frame.phase for frame in trajectory.keyframes}
    assert {"ZOOM_IN", "HOLD", "ZOOM_OUT"} <= phases
    assert trajectory.has_zoom
    assert trajectory.keyframes[0].zoom == pytest.approx(1.0)
    assert trajectory.keyframes[-1].zoom == pytest.approx(1.0, abs=0.02)
    peak = max(frame.zoom for frame in trajectory.keyframes)
    assert peak == pytest.approx(2.0, abs=0.01)


def test_crop_never_leaves_source_frame():
    config = ReframeConfig()
    moment = Moment(
        start_time=0.0,
        end_time=1.0,
        confidence=0.9,
        moment_score=0.8,
        target_id=1,
        recommended_zoom=2.0,
    )
    # Subjek di pojok: kamera harus tetap di dalam frame.
    samples = [(index / 30.0, 1, 5.0, 5.0) for index in range(30)]
    trajectory = build_trajectory(
        config=config,
        moments=[moment],
        samples=samples,
        duration=1.0,
        src_w=SRC_W,
        src_h=SRC_H,
        target_ratio=9 / 16,
        output_fps=30,
    )
    for frame in trajectory.keyframes:
        assert frame.x >= 0 and frame.y >= 0
        assert frame.x + frame.w <= SRC_W + 0.5
        assert frame.y + frame.h <= SRC_H + 0.5


def test_disabled_zoom_ignores_moments():
    config = ReframeConfig(enable_auto_zoom=False)
    moment = Moment(
        start_time=0.0,
        end_time=1.0,
        confidence=0.9,
        moment_score=0.8,
        target_id=1,
        recommended_zoom=2.0,
    )
    trajectory = build_trajectory(
        config=config,
        moments=[moment],
        samples=[(index / 30.0, 1, 640.0, 360.0) for index in range(30)],
        duration=1.0,
        src_w=SRC_W,
        src_h=SRC_H,
        target_ratio=9 / 16,
        output_fps=30,
    )
    assert not trajectory.has_zoom
    assert any("auto_zoom disabled" in note for note in trajectory.notes)