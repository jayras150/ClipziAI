"""
Laporan analisis JSON untuk debugging & verifikasi keputusan zoom.

Isinya menjawab pertanyaan "kenapa kamera melakukan (atau tidak melakukan)
zoom di sini" tanpa harus membaca log panjang.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from app.services.reframe.config import ReframeConfig
from app.services.reframe.features import FrameFeatures
from app.services.reframe.moments import Moment, MomentResult
from app.services.reframe.trajectory import CameraTrajectory


def build_report(
    config: ReframeConfig,
    duration: float,
    features: Sequence[FrameFeatures],
    moment_result: MomentResult,
    trajectory: Optional[CameraTrajectory],
    detector_info: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    max_decisions: int = 400,
) -> Dict[str, Any]:
    """Ringkas seluruh keputusan analisis menjadi satu dokumen JSON."""
    person_ids = {
        item.primary_id for item in features if item.primary_id is not None
    }
    sample_count = len(features)
    with_person = sum(1 for item in features if item.person_count > 0)
    zoom_events = trajectory.events if trajectory else []
    phases: Dict[str, int] = {}
    if trajectory:
        for frame in trajectory.keyframes:
            phases[frame.phase] = phases.get(frame.phase, 0) + 1

    decisions: List[Dict[str, Any]] = []
    for decision in moment_result.decisions[:max_decisions]:
        decisions.append(
            {
                "time": round(decision.time, 3),
                "score": round(decision.score, 4),
                "accepted": decision.accepted,
                "reason": decision.reason,
                "target_id": decision.target_id,
            }
        )

    report: Dict[str, Any] = {
        "video_duration": round(float(duration), 3),
        "analysis_fps": config.analysis_fps,
        "samples": sample_count,
        "samples_with_person": with_person,
        "detected_persons": len(person_ids),
        "person_ids": sorted(pid for pid in person_ids if pid is not None),
        "selected_moments": len(moment_result.moments),
        "zoom_events": len(zoom_events),
        "zoom_skipped": moment_result.skipped,
        "skip_reasons": dict(moment_result.skip_reasons),
        "tracking_events": len(person_ids),
        "zoom_phases": phases,
        "zoom_enabled": config.enable_auto_zoom,
        "follow_enabled": config.enable_camera_follow,
        "moments": [moment.to_dict() for moment in moment_result.moments],
        "zoom_event_details": [event.to_dict() for event in zoom_events],
        "decisions": decisions,
        "notes": list(trajectory.notes) if trajectory else [],
        "config": config.to_dict(),
    }
    if detector_info:
        report["detectors"] = detector_info
    if extra:
        report.update(extra)
    return report


def summarize_moment(moment: Moment) -> str:
    return (
        f"{moment.start_time:.2f}-{moment.end_time:.2f}s "
        f"score={moment.moment_score:.2f} zoom={moment.recommended_zoom:.2f} "
        f"target={moment.target_id} ({moment.reason})"
    )