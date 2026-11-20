"""
Virtual camera: state machine zoom + camera follow yang smooth.

Zoom (state machine, per frame):

    NORMAL --ramp in--> HOLD --ramp out--> NORMAL

    * ZOOM_IN / ZOOM_OUT memakai easing (smoothstep) sehingga tidak ada
      lompatan ukuran crop;
    * HOLD berhenti di `recommended_zoom` momen tersebut;
    * cooldown setelah ZOOM_OUT mencegah zoom berkedip;
    * tanpa momen valid -> zoom tetap 1.0 (framing asli).

Camera follow (independen dari zoom):

    * dead zone: kamera diam saat subjek masih di zona tengah;
    * EMA + batas kecepatan per frame;
    * motion prediction ringan untuk gerak konstan;
    * edge protection: crop tidak pernah keluar dari frame sumber;
    * grace period: target hilang sesaat -> kamera menahan posisi, TIDAK
      langsung mengejar objek lain.

Output: satu keyframe per frame output (x, y, w, h) yang siap dipakai
`sendcmd` + filter crop (runtime w/h sudah diverifikasi di FFmpeg image).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.reframe.config import ReframeConfig
from app.services.reframe.moments import Moment


def _clamp(value: float, low: float, high: float) -> float:
    return high if value > high else (low if value < low else value)


def smoothstep(t: float) -> float:
    t = _clamp(float(t), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


@dataclass
class CameraKeyframe:
    time: float
    x: float
    y: float
    w: float
    h: float
    zoom: float = 1.0
    phase: str = "NORMAL"
    target_id: Optional[int] = None

    def as_tuple(self) -> Tuple[float, float, float, float, float]:
        return (self.time, self.x, self.y, self.w, self.h)

    def to_dict(self) -> Dict[str, object]:
        return {
            "time": round(self.time, 3),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "w": round(self.w, 2),
            "h": round(self.h, 2),
            "zoom": round(self.zoom, 4),
            "phase": self.phase,
            "target_id": self.target_id,
        }


@dataclass
class ZoomEvent:
    start_time: float
    end_time: float
    peak_zoom: float
    target_id: Optional[int]
    moment_index: int
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "peak_zoom": round(self.peak_zoom, 4),
            "target_id": self.target_id,
            "moment_index": self.moment_index,
            "reason": self.reason,
        }


@dataclass
class CameraTrajectory:
    keyframes: List[CameraKeyframe] = field(default_factory=list)
    events: List[ZoomEvent] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    follow_enabled: bool = True
    zoom_enabled: bool = True

    @property
    def has_zoom(self) -> bool:
        return any(abs(frame.zoom - 1.0) > 1e-3 for frame in self.keyframes)

    def as_tuples(self) -> List[Tuple[float, float, float, float, float]]:
        return [frame.as_tuple() for frame in self.keyframes]


def crop_window(
    src_w: int,
    src_h: int,
    target_ratio: float,
    zoom: float,
) -> Tuple[float, float]:
    """
    Ukuran jendela crop (genap) untuk rasio target pada zoom tertentu.

    zoom = 1.0 -> jendela terbesar yang muat (framing asli untuk rasio itu).
    """
    zoom = max(1.0, float(zoom))
    if src_w / src_h > target_ratio:
        win_h = src_h / zoom
        win_w = win_h * target_ratio
    else:
        win_w = src_w / zoom
        win_h = win_w / target_ratio
    win_w = min(float(src_w), win_w)
    win_h = min(float(src_h), win_h)
    win_w = max(2, int(win_w) - int(win_w) % 2)
    win_h = max(2, int(win_h) - int(win_h) % 2)
    return float(win_w), float(win_h)


def build_trajectory(
    config: ReframeConfig,
    moments: Sequence[Moment],
    samples: Sequence[Tuple[float, Optional[int], float, float]],
    duration: float,
    src_w: int,
    src_h: int,
    target_ratio: float,
    output_fps: int,
) -> CameraTrajectory:
    """
    Bangun jalur kamera per frame output.

    `samples` = (time, target_id, cx, cy) hasil tracking untuk camera follow.
    `moments` = momen tervalidasi (boleh kosong -> framing asli).
    """
    cfg = config.sanitized()
    trajectory = CameraTrajectory(
        follow_enabled=cfg.enable_camera_follow, zoom_enabled=cfg.enable_auto_zoom
    )
    fps = max(1, int(output_fps))
    total_frames = max(1, int(round(duration * fps)))

    base_w, base_h = crop_window(src_w, src_h, target_ratio, 1.0)
    center_x = (src_w - base_w) / 2.0
    center_y = (src_h - base_h) / 2.0

    # --- jadwal zoom per frame (state machine) ---
    zoom_curve: List[float] = [1.0] * total_frames
    phase_curve: List[str] = ["NORMAL"] * total_frames
    moment_curve: List[Optional[int]] = [None] * total_frames
    active_moments = list(moments) if cfg.enable_auto_zoom else []
    if not cfg.enable_auto_zoom and moments:
        trajectory.notes.append("auto_zoom disabled: moments ignored")

    ramp_in = max(1, int(round(cfg.zoom_in_duration * fps)))
    ramp_out = max(1, int(round(cfg.zoom_out_duration * fps)))
    cooldown_frames = int(round(cfg.zoom_cooldown * fps))
    last_zoom_out_end = -10**9

    for moment_index, moment in enumerate(active_moments):
        start = int(round(moment.start_time * fps))
        end = int(round(moment.end_time * fps))
        start = max(0, min(total_frames, start))
        end = max(start, min(total_frames, end))
        if end - start < 1:
            continue
        if start - last_zoom_out_end < cooldown_frames:
            trajectory.notes.append(
                f"moment {moment_index} skipped: cooldown ({moment.start_time:.2f}s)"
            )
            continue
        peak = _clamp(moment.recommended_zoom, cfg.minimum_zoom, cfg.maximum_zoom)
        if peak <= 1.0 + 1e-6:
            trajectory.notes.append(
                f"moment {moment_index} skipped: recommended zoom ~1.0"
            )
            continue
        hold_start = min(end, start + ramp_in)
        hold_end = max(hold_start, end - ramp_out)
        event_start = start
        for frame in range(start, end):
            if frame < hold_start:
                progress = smoothstep((frame - start + 1) / max(1, ramp_in))
                zoom_curve[frame] = 1.0 + (peak - 1.0) * progress
                phase_curve[frame] = "ZOOM_IN"
            elif frame < hold_end:
                zoom_curve[frame] = peak
                phase_curve[frame] = "HOLD"
            else:
                progress = smoothstep((frame - hold_end + 1) / max(1, ramp_out))
                zoom_curve[frame] = peak + (1.0 - peak) * progress
                phase_curve[frame] = "ZOOM_OUT"
            moment_curve[frame] = moment_index
        trajectory.events.append(
            ZoomEvent(
                start_time=event_start / fps,
                end_time=end / fps,
                peak_zoom=peak,
                target_id=moment.target_id,
                moment_index=moment_index,
                reason=moment.reason,
            )
        )
        last_zoom_out_end = end

    # --- camera follow: target center per frame ---
    ordered = sorted(samples, key=lambda item: item[0])
    sample_times = [item[0] for item in ordered]

    def target_at(time_value: float, target_id: Optional[int]) -> Optional[Tuple[float, float]]:
        if not ordered:
            return None
        best: Optional[Tuple[float, float]] = None
        best_delta = 1e9
        for item in ordered:
            if target_id is not None and item[1] != target_id:
                continue
            delta = abs(item[0] - time_value)
            if delta < best_delta:
                best_delta = delta
                best = (item[2], item[3])
            elif item[0] > time_value and best is not None:
                break
        return best

    keyframes: List[CameraKeyframe] = []
    cam_x, cam_y = center_x, center_y
    velocity_x, velocity_y = 0.0, 0.0
    lost_frames = 0
    grace_frames = max(1, int(round(cfg.tracking_grace_period * fps)))
    alpha = _clamp(cfg.camera_smoothing, 0.0, 0.95)
    max_step_x = max(1.0, base_w * cfg.camera_max_velocity)
    max_step_y = max(1.0, base_h * cfg.camera_max_velocity)

    for frame in range(total_frames):
        time_value = frame / fps
        zoom = zoom_curve[frame]
        win_w, win_h = crop_window(src_w, src_h, target_ratio, zoom)
        moment_index = moment_curve[frame]
        target_id = (
            active_moments[moment_index].target_id
            if moment_index is not None and moment_index < len(active_moments)
            else None
        )

        follow_allowed = cfg.enable_camera_follow
        desired: Optional[Tuple[float, float]] = None
        if follow_allowed:
            desired = target_at(time_value, target_id)
            if desired is None and target_id is not None:
                # target momen hilang: tahan posisi selama grace period
                lost_frames += 1
                if lost_frames <= grace_frames:
                    desired = (cam_x + win_w / 2.0, cam_y + win_h / 2.0)
            elif desired is not None:
                lost_frames = 0
            if desired is None:
                # subjek hilang total -> kembali ke tengah secara smooth
                desired = (src_w / 2.0, src_h / 2.0)

        if desired is not None:
            target_x = desired[0] - win_w / 2.0
            target_y = desired[1] - win_h / 2.0
            # motion prediction: dorong sedikit ke arah gerak (dibatasi)
            pred = _clamp(cfg.camera_motion_prediction, 0.0, 1.0)
            target_x += velocity_x * pred
            target_y += velocity_y * pred

            dead_x = win_w * cfg.camera_dead_zone
            dead_y = win_h * cfg.camera_dead_zone
            delta_x = target_x - cam_x
            delta_y = target_y - cam_y

            if abs(delta_x) > dead_x:
                step_x = (delta_x - (dead_x if delta_x > 0 else -dead_x)) * (1.0 - alpha)
                step_x = _clamp(step_x, -max_step_x * (win_w / base_w), max_step_x * (win_w / base_w))
                cam_x += step_x
                velocity_x = 0.7 * velocity_x + 0.3 * step_x
            else:
                velocity_x *= 0.6
            if abs(delta_y) > dead_y:
                step_y = (delta_y - (dead_y if delta_y > 0 else -dead_y)) * (1.0 - alpha)
                step_y = _clamp(step_y, -max_step_y * (win_h / base_h), max_step_y * (win_h / base_h))
                cam_y += step_y
                velocity_y = 0.7 * velocity_y + 0.3 * step_y
            else:
                velocity_y *= 0.6

        # edge protection: crop tidak boleh keluar frame sumber
        cam_x = _clamp(cam_x, 0.0, max(0.0, src_w - win_w))
        cam_y = _clamp(cam_y, 0.0, max(0.0, src_h - win_h))

        keyframes.append(
            CameraKeyframe(
                time=time_value,
                x=cam_x,
                y=cam_y,
                w=win_w,
                h=win_h,
                zoom=zoom,
                phase=phase_curve[frame],
                target_id=target_id,
            )
        )

    trajectory.keyframes = keyframes
    if not cfg.enable_camera_follow:
        trajectory.notes.append("camera_follow disabled: static center crop")
    return trajectory