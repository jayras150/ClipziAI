"""
AI Moment-Based Auto Reframing.

Pipeline (dipisah supaya inferensi dan rendering tidak saling menunggu):

    analysis   -> sample frame + deteksi (YOLO11n person, YuNet face) + tracking
    moments    -> Moment Detection Engine (skor + kandidat momen)
    trajectory -> virtual camera (zoom state machine + camera follow smoothing)
    render     -> FFmpeg (sendcmd + crop runtime w/h, terverifikasi smoke test)

Modul ini TIDAK memanggil ffmpeg dan TIDAK menulis video; `VideoProcessor`
tetap menjadi satu-satunya renderer. Semua kelas di sini murni komputasi
sehingga bisa diuji tanpa GPU maupun video nyata.
"""
from app.services.reframe.config import ReframeConfig, load_reframe_config
from app.services.reframe.tracker import ByteTrackLite, Track
from app.services.reframe.features import FrameFeatures, extract_features
from app.services.reframe.moments import Moment, MomentDetectionEngine
from app.services.reframe.trajectory import CameraKeyframe, CameraTrajectory, build_trajectory
from app.services.reframe.report import build_report

__all__ = [
    "ReframeConfig",
    "load_reframe_config",
    "ByteTrackLite",
    "Track",
    "FrameFeatures",
    "extract_features",
    "Moment",
    "MomentDetectionEngine",
    "CameraKeyframe",
    "CameraTrajectory",
    "build_trajectory",
    "build_report",
]