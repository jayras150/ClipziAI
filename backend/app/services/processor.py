"""
Video Processor Service - FFmpeg, PySceneDetect, smart crop, burn subtitle
"""
import os
import asyncio
import functools
import hashlib
import json
import logging
import math
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.services.reframe.config import load_reframe_config
from app.services.reframe.detectors import get_face_detector, get_person_detector
from app.services.reframe.features import extract_features
from app.services.reframe.moments import MomentDetectionEngine
from app.services.reframe.report import build_report
from app.services.reframe.tracker import ByteTrackLite, track_strength
from app.services.reframe.trajectory import build_trajectory
from app.services.reframe.trajectory import crop_window as _reframe_crop_window

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class _FaceDetection:
    """Satu wajah pada satu frame sample (koordinat sumber)."""

    x: float
    y: float
    w: float
    h: float
    score: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)


@dataclass
class _FaceTrack:
    """Track wajah sederhana berbasis IoU/centroid (tanpa library tracker)."""

    track_id: int
    x: float
    y: float
    w: float
    h: float
    score: float
    hits: int = 1
    misses: int = 0
    last_seen: float = 0.0
    observations: List[Tuple[float, float, float, float, float, float]] = field(
        default_factory=list
    )

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def remember(self) -> None:
        self.observations.append(
            (self.last_seen, self.cx, self.cy, self.w, self.h, self.score)
        )


@dataclass
class _SubjectState:
    """State hysteresis pemilihan subjek utama."""

    primary_id: Optional[int] = None
    challenger_id: Optional[int] = None
    challenger_count: int = 0
    last_primary_seen: float = -999.0


@dataclass
class _SpeakerCropPlan:
    """Hasil analisis: jalur crop utama dan opsional jalur kedua untuk split."""

    primary: List[Tuple[float, float, float, float, float]] = field(default_factory=list)
    secondary: List[Tuple[float, float, float, float, float]] = field(
        default_factory=list
    )
    split: bool = False
    # --- AI moment-based reframing (jalur baru) ---
    # Keyframe kamera per frame: (t, x, y, w, h) dari `CameraTrajectory`.
    keyframes: List[Tuple[float, float, float, float, float]] = field(
        default_factory=list
    )
    analysis: Dict[str, Any] = field(default_factory=dict)
    has_zoom: bool = False

# ---------------------------------------------------------------------------
# Preset gaya caption/subtitle (dipakai UI "Style subtitle").
#
# `force_style` menata subtitle SRT yang dibakar libass. Nilai FontSize/MarginV
# memakai satuan PlayResY=288 milik demuxer SRT ffmpeg: 16 = ukuran bawaan,
# 18-20 terasa lebih besar, 19 + Bold = gaya "hook" khas TikTok/Reels.
#
# `overlay` menata caption teks manual (drawtext). `size_ratio` adalah tinggi
# font dibagi tinggi output supaya ukurannya ikut resolusi (1080x1920, 1:1,
# maupun 16:9), `y` menentukan posisi vertikal.
# ---------------------------------------------------------------------------
CAPTION_STYLES: Dict[str, Dict[str, Any]] = {
    "classic": {
        "label": "Classic putih",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1.6,Shadow=0,Alignment=2,MarginV=22"
        ),
        "overlay": {
            "size_ratio": 0.050,
            "color": "white",
            "border_width": 3,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "gold": {
        "label": "Gold tebal",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H006BC7F4,"
            "OutlineColour=&H00000000,Outline=2.2,Shadow=0,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.062,
            "color": "0xF4C76B",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "boxed": {
        "label": "Kotak hitam",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "BorderStyle=3,OutlineColour=&H00000000,BackColour=&H80000000,"
            "Outline=1,Shadow=0,Alignment=2,MarginV=22"
        ),
        "overlay": {
            "size_ratio": 0.050,
            "color": "white",
            "border_width": 0,
            "border_color": "black",
            "box": True,
            "box_color": "black@0.62",
            "y": "bottom",
        },
    },
    "neon": {
        "label": "Neon cyan",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00DCE97C,"
            "OutlineColour=&H00000000,Outline=2.4,Shadow=0,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.060,
            "color": "0x7CE9DC",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "top": {
        "label": "Atas bersih",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1.6,Shadow=0,Alignment=8,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.050,
            "color": "white",
            "border_width": 3,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "top",
        },
    },
    "center": {
        "label": "Hook tengah",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=19,PrimaryColour=&H006BC7F4,"
            "OutlineColour=&H00000000,Outline=2.6,Shadow=0,Bold=1,Alignment=5,MarginV=0"
        ),
        "overlay": {
            "size_ratio": 0.066,
            "color": "0xF4C76B",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "center",
        },
    },
    "karaoke": {
        "label": "Karaoke gold",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&I00FFFFFF,"
            "SecondaryColour=&H006BC7F4,OutlineColour=&H00000000,Outline=2.8,"
            "Shadow=0,Bold=1,Alignment=2,MarginV=30"
        ),
        "overlay": {
            "size_ratio": 0.070,
            "color": "0xF4C76B",
            "border_width": 6,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "minimal": {
        "label": "Minimal clean",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=13,PrimaryColour=&H00F2F4F8,"
            "OutlineColour=&H00000000,Outline=0,Shadow=2,Alignment=2,MarginV=18"
        ),
        "overlay": {
            "size_ratio": 0.040,
            "color": "0xF2F4F8",
            "border_width": 0,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.55",
            "y": "bottom",
        },
    },
    "impact": {
        "label": "Impact bold",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=3.4,Shadow=0,Bold=1,Alignment=2,MarginV=26"
        ),
        "overlay": {
            "size_ratio": 0.078,
            "color": "white",
            "border_width": 7,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "boxed_gold": {
        "label": "Gold on black",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=15,PrimaryColour=&H006BC7F4,"
            "OutlineColour=&H00000000,Outline=1.2,Shadow=0,Bold=1,BorderStyle=3,"
            "BackColour=&H80000000,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.048,
            "color": "0xF4C76B",
            "border_width": 2,
            "border_color": "black",
            "box": True,
            "box_color": "black@0.72",
            "y": "bottom",
        },
    },
    "pink": {
        "label": "Neon pink",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00B07BFF,"
            "OutlineColour=&H00201018,Outline=2.4,Shadow=1,Bold=1,Alignment=2,MarginV=26"
        ),
        "overlay": {
            "size_ratio": 0.060,
            "color": "0xFF7BC0",
            "border_width": 5,
            "border_color": "0x1A0C14",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "top_clean": {
        "label": "Headline top",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1.8,Shadow=0,Bold=1,Alignment=8,MarginV=26"
        ),
        "overlay": {
            "size_ratio": 0.052,
            "color": "white",
            "border_width": 4,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "top",
        },
    },
    "subtitle_bar": {
        "label": "Caption bar",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=14,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1,Bold=1,BorderStyle=4,"
            "BackColour=&HB0000000,Alignment=2,MarginV=20"
        ),
        "overlay": {
            "size_ratio": 0.044,
            "color": "white",
            "border_width": 2,
            "border_color": "black",
            "box": True,
            "box_color": "black@0.7",
            "y": "bottom",
        },
    },
    # --- Variasi warna tambahan (25 kartu di dashboard) ---------------------
    "mint": {
        "label": "Mint pop",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00C4FF7C,"
            "OutlineColour=&H00000000,Outline=2.4,Shadow=0,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.060,
            "color": "0x7CFFC4",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "sunset": {
        "label": "Sunset",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=17,PrimaryColour=&H006BA4FF,"
            "OutlineColour=&H00000000,Outline=2.2,Shadow=1,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.056,
            "color": "0xFFA46B",
            "border_width": 4,
            "border_color": "0x3A1A08",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "violet": {
        "label": "Violet glow",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FF9BC7,"
            "OutlineColour=&H00140A1C,Outline=2.4,Shadow=1,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.058,
            "color": "0xC79BFF",
            "border_width": 4,
            "border_color": "0x140A1C",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "lemon": {
        "label": "Lemon pop",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=17,PrimaryColour=&H006BE8FF,"
            "OutlineColour=&H00000000,Outline=2.6,Shadow=0,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.056,
            "color": "0xFFE86B",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "ice": {
        "label": "Ice blue box",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=14,PrimaryColour=&H00FFD89F,"
            "OutlineColour=&H00000000,Outline=1,Bold=1,BorderStyle=3,"
            "BackColour=&H80061220,Alignment=2,MarginV=22"
        ),
        "overlay": {
            "size_ratio": 0.046,
            "color": "0x9FD8FF",
            "border_width": 1,
            "border_color": "black",
            "box": True,
            "box_color": "0x061220@0.8",
            "y": "bottom",
        },
    },
    "crimson": {
        "label": "Crimson bold",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H006B6BFF,"
            "OutlineColour=&H00000000,Outline=2.6,Shadow=0,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.060,
            "color": "0xFF6B6B",
            "border_width": 5,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "mono": {
        "label": "Mono tag",
        "force_style": (
            "FontName=DejaVu Sans Mono,FontSize=14,PrimaryColour=&H00EDEDED,"
            "OutlineColour=&H00000000,Outline=1,Shadow=0,BorderStyle=3,"
            "BackColour=&H90000000,Alignment=2,MarginV=20"
        ),
        "overlay": {
            "size_ratio": 0.044,
            "color": "0xEDEDED",
            "border_width": 1,
            "border_color": "black",
            "box": True,
            "box_color": "black@0.72",
            "y": "bottom",
        },
    },
    "shadow": {
        "label": "Soft shadow",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,Outline=1,Shadow=3,Bold=1,Alignment=2,MarginV=24"
        ),
        "overlay": {
            "size_ratio": 0.052,
            "color": "white",
            "border_width": 2,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "bottom",
        },
    },
    "teal_box": {
        "label": "Teal box",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=15,PrimaryColour=&H00D7E76E,"
            "OutlineColour=&H00000000,Outline=1,Bold=1,BorderStyle=3,"
            "BackColour=&H80000000,Alignment=2,MarginV=22"
        ),
        "overlay": {
            "size_ratio": 0.048,
            "color": "0x6EE7D7",
            "border_width": 1,
            "border_color": "black",
            "box": True,
            "box_color": "black@0.68",
            "y": "bottom",
        },
    },
    "amber_top": {
        "label": "Amber top",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H006BC4FF,"
            "OutlineColour=&H00000000,Outline=2.2,Shadow=0,Bold=1,Alignment=8,MarginV=26"
        ),
        "overlay": {
            "size_ratio": 0.052,
            "color": "0xFFC46B",
            "border_width": 4,
            "border_color": "black",
            "box": False,
            "box_color": "black@0.6",
            "y": "top",
        },
    },
    "magenta_center": {
        "label": "Magenta center",
        "force_style": (
            "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00D18BFF,"
            "OutlineColour=&H00240F1C,Outline=3,Shadow=1,Bold=1,Alignment=5,MarginV=0"
        ),
        "overlay": {
            "size_ratio": 0.070,
            "color": "0xFF8BD1",
            "border_width": 6,
            "border_color": "0x240F1C",
            "box": False,
            "box_color": "black@0.6",
            "y": "center",
        },
    },
}



def get_caption_style(name: Optional[str]) -> Dict[str, Any]:
    """Ambil preset gaya caption; nama tak dikenal jatuh ke `classic`."""
    key = (name or "").strip().lower()
    return CAPTION_STYLES.get(key, CAPTION_STYLES["classic"])


class VideoProcessor:
    """Process videos: scene detection, smart crop 9:16, burn subtitle, compress."""
    
    def __init__(self, work_dir: str = "./work"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        # Sekali per proses: catat encoder yang benar-benar dipakai supaya
        # fallback ke CPU kelihatan jelas di log worker (bukan diam-diam).
        self.nvenc_available()

    # ------------------------------------------------------------------
    # Encoder: NVENC (GPU) bila tersedia, kalau tidak libx264 (CPU).
    # ------------------------------------------------------------------
    _nvenc_ok: Optional[bool] = None

    @classmethod
    def nvenc_available(cls) -> bool:
        """True bila ffmpeg bisa memakai h264_nvenc di mesin ini.

        Hasil di-cache per proses: probe hanya sekali supaya tidak menambah
        latensi di setiap render. Probe gagal (tanpa GPU, driver tidak ada,
        atau ffmpeg tanpa dukungan NVENC) berarti tetap di CPU.
        """
        if cls._nvenc_ok is not None:
            return cls._nvenc_ok

        if (os.getenv("FFMPEG_ENCODER") or "").strip().lower() in {"cpu", "libx264"}:
            cls._nvenc_ok = False
            logger.info("Encoder video: libx264 (dipaksa lewat FFMPEG_ENCODER)")
            return False

        ok = False
        try:
            probe = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-nostdin", "-y",
                    "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                    "-frames:v", "1",
                    "-c:v", "h264_nvenc",
                    "-f", "null", "-",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            ok = probe.returncode == 0
            if not ok:
                logger.info(
                    "Encoder video: libx264 (NVENC tidak bisa dipakai: %s)",
                    (probe.stderr or "").strip().splitlines()[-1:] or "unknown",
                )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("Encoder video: libx264 (probe NVENC gagal: %s)", exc)

        if ok:
            logger.info("Encoder video: h264_nvenc (GPU)")
        cls._nvenc_ok = ok
        return ok

    @classmethod
    def video_encode_args(cls, crf: int = 21, preset: str = "veryfast") -> List[str]:
        """Argumen `-c:v ...` untuk ffmpeg: NVENC bila ada, selain itu libx264.

        Kualitas disetarakan: `-cq` NVENC kira-kira setara `-crf` x264, dan
        `-preset p4` setara `veryfast`. `-rc vbr` + `-b:v 0` membuat NVENC
        benar-benar mode kualitas konstan, bukan bitrate tetap.
        """
        if cls.nvenc_available():
            return [
                "-c:v", "h264_nvenc",
                "-preset", "p4",
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", str(crf),
                "-b:v", "0",
                "-pix_fmt", "yuv420p",
            ]
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    
    @staticmethod
    def _video_duration_sync(video_path: str) -> float:
        """Durasi video (detik) — murah, hanya membaca metadata container."""
        import cv2

        cap = cv2.VideoCapture(video_path)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            return float(frames) / float(fps) if fps else 0.0
        finally:
            cap.release()

    async def detect_scenes(self, video_path: str) -> List[Dict[str, Any]]:
        """Deteksi scene, dengan batas durasi agar video panjang tidak lambat.

        Scene detection hanya dipakai sebagai FALLBACK saat perencanaan berbasis
        transkrip tidak menghasilkan rentang. Biayanya terukur 94s untuk video
        1080p 10 menit (≈9 menit untuk 1 jam). Untuk video di atas
        `SCENE_DETECT_MAX_MINUTES` (default 20) kita lewati dan biarkan
        `_select_clip_ranges` membagi durasi merata — jauh lebih hemat dengan
        dampak kualitas kecil.
        """
        try:
            from scenedetect import ContentDetector, detect  # noqa: F401
        except ImportError:
            return [{"start": 0, "end": 60, "confidence": 1.0}]

        import os

        max_minutes = float(os.getenv("SCENE_DETECT_MAX_MINUTES", "20") or 20)
        loop = asyncio.get_event_loop()
        duration = await loop.run_in_executor(
            None, self._video_duration_sync, video_path
        )
        if max_minutes > 0 and duration > max_minutes * 60:
            logger.info(
                "Scene detection dilewati: durasi %.1f menit > batas %.0f menit "
                "(rentang klip dibagi merata)",
                duration / 60,
                max_minutes,
            )
            return []

        return await loop.run_in_executor(None, self._detect_scenes_sync, video_path)

    def _detect_scenes_native(self, video_path: str) -> List[Dict[str, Any]]:
        """PySceneDetect penuh (histogram tiap frame). Akurat tapi lambat:
        terukur 94s untuk video 1080p 10 menit, dan >9 menit untuk video 1 jam.
        Dipakai sebagai fallback / saat SCENE_DETECT_MODE=native."""
        from scenedetect import ContentDetector, detect

        scenes = detect(video_path, ContentDetector(min_scene_len=5))
        logger.info("Scene detection: %s scene (PySceneDetect penuh)", len(scenes))
        return [
            {
                "start": start_time.get_seconds(),
                "end": end_time.get_seconds(),
                "confidence": 1.0,
            }
            for start_time, end_time in scenes
        ]

    def _detect_scenes_sampling(self, video_path: str) -> List[Dict[str, Any]]:
        """Deteksi scene cepat: sampling 1 frame/N detik + refine sekitar cut.

        Mengapa: PySceneDetect 0.7 menghitung histogram SETIAP frame pada
        resolusi penuh — itu sumber utama waktu proses (94s untuk 10 menit
        1080p). Sampling pada 160x90 dengan lompatan waktu jauh lebih murah,
        lalu kandidat cut di-refine pada 0.25s agar batas scene tetap presisi.

        Env:
          SCENE_DETECT_MODE      = sampling (default) | native
          SCENE_SAMPLE_SECONDS   = 2   (jarak antar sample)
          SCENE_CUT_THRESHOLD    = 18  (mean abs diff 0-255 untuk cut)
        """
        import os

        import cv2
        import numpy as np

        step = max(0.5, float(os.getenv("SCENE_SAMPLE_SECONDS", "2") or 2))
        threshold = float(os.getenv("SCENE_CUT_THRESHOLD", "18") or 18)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("video tidak bisa dibuka")
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            duration = float(frames) / fps if fps > 0 else 0.0
            if duration <= 0:
                raise RuntimeError("durasi video tidak diketahui")

            diffs: List[tuple] = []
            prev = None
            stamp = 0.0
            while stamp < duration:
                cap.set(cv2.CAP_PROP_POS_MSEC, stamp * 1000.0)
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(
                    cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA),
                    cv2.COLOR_BGR2GRAY,
                )
                if prev is not None:
                    diffs.append((stamp, float(np.mean(cv2.absdiff(gray, prev)))))
                prev = gray
                stamp += step
        finally:
            cap.release()

        candidates = [stamp for stamp, diff in diffs if diff >= threshold]

        # Refine tiap kandidat pada jendela ±step dengan resolusi 0.25s.
        cuts: List[float] = []
        if candidates:
            cap = cv2.VideoCapture(video_path)
            try:
                for cut in candidates:
                    start = max(0.0, cut - step)
                    end = min(duration, cut + step)
                    best_at, best_diff, prev = cut, -1.0, None
                    stamp = start
                    while stamp <= end:
                        cap.set(cv2.CAP_PROP_POS_MSEC, stamp * 1000.0)
                        ok, frame = cap.read()
                        if not ok:
                            break
                        gray = cv2.cvtColor(
                            cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA),
                            cv2.COLOR_BGR2GRAY,
                        )
                        if prev is not None:
                            diff = float(np.mean(cv2.absdiff(gray, prev)))
                            if diff > best_diff:
                                best_at, best_diff = stamp, diff
                        prev = gray
                        stamp += 0.25
                    cuts.append(round(best_at, 2))
            finally:
                cap.release()

        points = sorted({0.0, *cuts})
        scenes: List[Dict[str, Any]] = []
        for index, start in enumerate(points):
            end = points[index + 1] if index + 1 < len(points) else round(duration, 2)
            if end - start >= 0.5:
                scenes.append(
                    {"start": round(start, 2), "end": round(end, 2), "confidence": 1.0}
                )
        if not scenes:
            scenes = [{"start": 0.0, "end": round(duration, 2), "confidence": 1.0}]
        logger.info(
            "Scene detection: %s scene (sampling %.1fs/160x90, %s kandidat cut)",
            len(scenes),
            step,
            len(cuts),
        )
        return scenes

    def _detect_scenes_sync(self, video_path: str) -> List[Dict[str, Any]]:
        """Pilih metode deteksi scene: sampling cepat, fallback PySceneDetect."""
        import os

        mode = (os.getenv("SCENE_DETECT_MODE") or "sampling").strip().lower()
        if mode == "native":
            return self._detect_scenes_native(video_path)
        try:
            return self._detect_scenes_sampling(video_path)
        except Exception as exc:  # noqa: BLE001 - jangan gagalkan pipeline
            logger.warning(
                "Scene detection sampling gagal (%s); memakai PySceneDetect penuh", exc
            )
            return self._detect_scenes_native(video_path)
        return [
            {
                "start": start_time.get_seconds(),
                "end": end_time.get_seconds(),
                "confidence": 1.0,
            }
            for start_time, end_time in scenes
        ]
    @staticmethod
    def _target_dimensions() -> tuple[int, int]:
        """Resolusi output (lebar, tinggi) dari settings.OUTPUT_RESOLUTION.

        Nilai dipaksa genap karena libx264 dengan yuv420p menolak dimensi ganjil.
        """
        raw = (settings.OUTPUT_RESOLUTION or "1080x1920").lower().replace(" ", "")
        try:
            width_str, height_str = raw.split("x", 1)
            width, height = int(width_str), int(height_str)
        except (ValueError, AttributeError):
            width, height = 1080, 1920
        if width <= 0 or height <= 0:
            width, height = 1080, 1920
        return width - (width % 2), height - (height % 2)

    def _dimensions_for_ratio(self, aspect_ratio: str) -> tuple[int, int]:
        """
        Dimensi output untuk aspect ratio tertentu.

        Sisi pendek mengikuti sisi pendek OUTPUT_RESOLUTION (default 1080), sisi
        panjang dihitung dari rasio. Jadi:
          9:16 -> 1080x1920, 1:1 -> 1080x1080, 16:9 -> 1920x1080.
        Versi lama selalu memakai 1080x1920 sehingga klip 1:1/16:9 ditarik
        kembali menjadi vertikal (distorsi).
        """
        base_w, base_h = self._target_dimensions()
        short = min(base_w, base_h)
        try:
            num, den = aspect_ratio.replace(" ", "").split(":", 1)
            ratio = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            ratio = 9 / 16

        if ratio >= 1:
            width, height = round(short * ratio), short
        else:
            width, height = short, round(short / ratio)

        return width - (width % 2), height - (height % 2)

    @staticmethod
    def _ratio_value(aspect_ratio: str) -> float:
        """'9:16' -> 0.5625. Nilai rusak jatuh ke 9:16 (default project)."""
        try:
            num, den = str(aspect_ratio).replace(" ", "").split(":", 1)
            ratio = float(num) / float(den)
            if ratio <= 0:
                raise ValueError
            return ratio
        except (ValueError, ZeroDivisionError, AttributeError):
            return 9.0 / 16.0

    def _probe_dimensions(self, input_path: str) -> Tuple[int, int]:
        """(width, height) video sumber; (0, 0) bila tidak terbaca."""
        try:
            out = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0", input_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            text = (out.stdout or "").strip().splitlines()
            if text:
                width_str, height_str = text[0].split("x")[:2]
                return int(width_str), int(height_str)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            logger.warning("ffprobe dimensi gagal (%s): %s", input_path, exc)
        return 0, 0

    async def smart_crop_aspect(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        aspect_ratio: str = "9:16",
        face_detect: bool = True,
    ) -> str:
        """
        Potong ke aspect ratio yang diinginkan (9:16, 1:1, 16:9) lalu scale ke
        resolusi target. Untuk sumber portrait/landscape/square apa pun hasilnya
        selalu rasio yang diminta, tidak pernah terpotong sempit aneh.
        """
        width, height = self._dimensions_for_ratio(aspect_ratio)
        num, den = aspect_ratio.replace(" ", "").split(":", 1)
        target_ratio = float(num) / float(den)

        # Ambil area dengan rasio target yang TERBESAR muat di frame (center).
        filter_chain = (
            "crop="
            f"w='2*trunc(min(iw,ih*{target_ratio})/2)':"
            f"h='2*trunc(min(ih,iw/{target_ratio})/2)':"
            "x='(iw-ow)/2':"
            "y='(ih-oh)/2',"
            f"scale={width}:{height}:flags=lanczos,"
            "setsar=1"
        )

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-vf", filter_chain,
            *self.video_encode_args(21),
            "-r", str(settings.OUTPUT_FPS),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def smart_crop_9x16(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        face_detect: bool = True,
    ) -> str:
        """Wrapper kompatibel dengan lama (aspect 9:16)."""
        return await self.smart_crop_aspect(input_path, output_path, start_time, duration, "9:16", face_detect)

    # Font yang tersedia di image produksi. Nama kunci dipakai di
    # editing_options.caption_font; path fallback pertama tetap DejaVu Sans Bold.
    CAPTION_FONT_FILES: Dict[str, List[str]] = {
        "sans": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ],
        "serif": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ],
        "mono": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        ],
    }

    @classmethod
    def resolve_font_file(cls, font_name: Optional[str] = None) -> Optional[str]:
        """Cari file font untuk drawtext; None bila tidak ada font sama sekali."""
        key = (font_name or "sans").strip().lower()
        candidates = list(cls.CAPTION_FONT_FILES.get(key, []))
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/Windows/Fonts/arialbd.ttf",
        ]
        return next((p for p in candidates if os.path.exists(p)), None)

    async def add_text_overlay(
        self,
        input_path: str,
        output_path: str,
        text: str,
        font_size: int = 24,
        font_color: str = "white",
        x: str = "(w-text_w)/2",
        y: str = "(h-text_h)/2",
        box: bool = True,
        box_color: str = "black@0.6",
        border_width: int = 0,
        border_color: str = "black",
        font_name: Optional[str] = None,
    ) -> str:
        """Bakar teks ke video dengan ffmpeg drawtext."""
        font_file = self.resolve_font_file(font_name)
        if not font_file:
            raise RuntimeError("Tidak ditemukan font TTF di container untuk caption.")

        # Tulis teks ke file lalu pakai `textfile=`. Cara ini bebas dari masalah
        # escaping filtergraph (apostrof, titik dua, '%', koma) yang membuat
        # drawtext gagal menggambar tanpa pesan error.
        text_file = str(Path(output_path).with_name(f"caption_{uuid4().hex}.txt"))
        Path(text_file).write_text(text, encoding="utf-8")

        drawtext = (
            f"drawtext=fontfile={self._escape_filter_path(font_file)}:"
            f"textfile={self._escape_filter_path(text_file)}:"
            f"fontsize={font_size}:"
            f"fontcolor={font_color}:"
            f"x={x}:"
            f"y={y}:"
            # expansion=none wajib: tanpa ini ffmpeg memperlakukan '%' sebagai
            # penanda strftime. Teks seperti "100%" jadi tidak tergambar.
            "expansion=none"
        )
        # Garis tepi (outline) membuat teks tetap terbaca di atas video terang.
        if border_width > 0:
            drawtext += f":borderw={int(border_width)}:bordercolor={border_color}"
        if box:
            drawtext += f":box=1:boxcolor={box_color}:boxborderw=8"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vf", drawtext,
            *self.video_encode_args(21),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        finally:
            try:
                os.remove(text_file)
            except OSError:
                pass
        return output_path

    @staticmethod
    def _escape_filter_text(text: str) -> str:
        """
        Escape teks untuk filter drawtext.

        Karakter '%' TIDAK diubah: filter memakai `expansion=none`, sehingga '%'
        dianggap literal. Sebelumnya '%' diubah jadi '%%' dan itu membuat
        drawtext tidak menggambar apa pun (ffmpeg memprosesnya sebagai strftime).
        """
        return text.replace("\\", "\\\\").replace("'", "\\'")

    async def change_speed(
        self,
        input_path: str,
        output_path: str,
        speed: float = 1.0,
    ) -> str:
        """
        Ubah kecepatan pemutaran (0.25x - 4x).
        Video: setpts=PTS/speed.  Audio: atempo (rentang 0.5-2.0, dirantai bila di luar).
        """
        if speed == 1.0:
            import shutil as _shutil
            _shutil.copyfile(input_path, output_path)
            return output_path

        vf = f"setpts=PTS/{speed}"
        atempo_chain = []
        remaining = speed
        while remaining > 2.0:
            atempo_chain.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            atempo_chain.append("atempo=0.5")
            remaining /= 0.5
        atempo_chain.append(f"atempo={remaining}")
        af = ",".join(atempo_chain)

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vf", vf,
            "-af", af,
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    # =====================================================================
    # Fase 2: filter warna, blur-fill, watermark, audio enhance, concat
    # =====================================================================
    FILTER_PRESETS = {
        "none": "",
        "warm": "eq=saturation=1.15:gamma_r=1.05:gamma_b=0.95",
        "cool": "eq=saturation=1.05:gamma_r=0.95:gamma_b=1.08",
        "cinematic": "curves=preset=medium_contrast,eq=saturation=0.9:contrast=1.05",
        "bw": "hue=s=0,eq=contrast=1.08",
        "vibrant": "eq=saturation=1.35:contrast=1.06",
        "vintage": "curves=vintage,noise=alls=6:allf=t+u",
    }

    @classmethod
    def filter_chain_for_preset(cls, preset: Optional[str]) -> str:
        """Nama preset -> potongan filter ffmpeg (string kosong bila tidak dikenal)."""
        return cls.FILTER_PRESETS.get((preset or "none").strip().lower(), "")

    async def render_clip(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        aspect_ratio: str = "9:16",
        filter_preset: Optional[str] = None,
        blur_fill: bool = False,
    ) -> str:
        """
        Render satu klip: potong rentang, reframe ke rasio target, opsional
        blur-fill (background blur untuk sumber landscape -> vertikal) dan
        opsional filter warna.

        `blur_fill` memakai filter_complex (split -> bg blur + video utama di
        tengah) sehingga sumber lebar tidak perlu dipotong habis.
        """
        width, height = self._dimensions_for_ratio(aspect_ratio)
        preset_chain = self.filter_chain_for_preset(filter_preset)

        cmd_base = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
        ]
        tail = [
            *self.video_encode_args(21),
            "-r", str(settings.OUTPUT_FPS),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        if blur_fill:
            chain = (
                f"[0:v]split=2[s0][s1];"
                f"[s0]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=28[bg];"
                f"[s1]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
                + (f",{preset_chain}" if preset_chain else "")
                + "[v]"
            )
            cmd = cmd_base + ["-filter_complex", chain, "-map", "[v]", "-map", "0:a?"] + tail
        else:
            num, den = aspect_ratio.replace(" ", "").split(":", 1)
            target_ratio = float(num) / float(den)
            chain = (
                "crop="
                f"w='2*trunc(min(iw,ih*{target_ratio})/2)':"
                f"h='2*trunc(min(ih,iw/{target_ratio})/2)':"
                "x='(iw-ow)/2':"
                "y='(ih-oh)/2',"
                f"scale={width}:{height}:flags=lanczos,"
                "setsar=1"
            )
            if preset_chain:
                chain = f"{chain},{preset_chain}"
            cmd = cmd_base + ["-vf", chain] + tail

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    # =====================================================================
    # Auto zoom follow-speaker (OpenCV + sendcmd crop animation)
    # =====================================================================
    @staticmethod
    def _face_detector(width: int, height: int):
        """
        Buat detektor wajah YuNet (cv2.FaceDetectorYN); None bila tidak tersedia.

        Catatan penting: OpenCV 5.x MENGHAPUS API lama `cv2.CascadeClassifier`
        (dan file XML haar tidak lagi dibundel), jadi deteksi wajah memakai
        model ONNX YuNet yang diunduh saat build ke /opt/opencv-data.
        """
        try:
            import cv2
        except ImportError:
            return None

        if not hasattr(cv2, "FaceDetectorYN"):
            return None

        candidates = [
            os.environ.get("OPENCV_FACE_MODEL", ""),
            "/opt/opencv-data/face_detection_yunet_2023mar.onnx",
        ]
        model_path = next((p for p in candidates if p and os.path.exists(p)), None)
        if not model_path:
            return None

        try:
            detector = cv2.FaceDetectorYN.create(
                model_path, "", (int(width), int(height)),
                score_threshold=0.6, nms_threshold=0.3, top_k=5000,
            )
            detector.setInputSize((int(width), int(height)))
            return detector
        except Exception:
            return None

    @staticmethod
    def _crop_window(
        src_w: int,
        src_h: int,
        target_ratio: float,
        zoom: float,
    ) -> Tuple[float, float]:
        """Ukuran jendela crop (genap) yang muat di frame sumber."""
        zoom = max(1.0, float(zoom or 1.0))
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

    @staticmethod
    def _face_iou(a: Any, b: Any) -> float:
        """IoU untuk objek yang punya atribut x/y/w/h."""
        ax1, ay1 = a.x, a.y
        ax2, ay2 = a.x + a.w, a.y + a.h
        bx1, by1 = b.x, b.y
        bx2, by2 = b.x + b.w, b.y + b.h
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
        intersection = iw * ih
        union = a.w * a.h + b.w * b.h - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _track_strength(track: _FaceTrack, src_w: int, src_h: int) -> float:
        """Skor subjek: confidence + ukuran + kedekatan tengah + umur track."""
        center_dist = math.hypot(track.cx - src_w / 2.0, track.cy - src_h / 2.0)
        center_bonus = max(0.0, 1.0 - center_dist / max(1.0, 0.75 * src_w))
        age_bonus = min(0.25, track.hits * 0.02)
        area_bonus = min(0.20, track.area / max(1.0, src_w * src_h) * 10.0)
        return track.score + 0.12 * center_bonus + age_bonus + area_bonus


    def _update_face_tracks(
        self,
        active: Dict[int, _FaceTrack],
        all_tracks: Dict[int, _FaceTrack],
        detections: List[_FaceDetection],
        now: float,
        next_id: int,
        max_missed: int = 6,
        alpha: float = 0.65,
    ) -> Tuple[Dict[int, _FaceTrack], int]:
        """Cocokkan deteksi ke track lama dengan IoU/centroid, lalu buat track baru."""
        pairs: List[Tuple[float, int, int]] = []
        for track_id, track in active.items():
            for det_index, det in enumerate(detections):
                iou = self._face_iou(track, det)
                distance = math.hypot(track.cx - det.cx, track.cy - det.cy)
                max_distance = max(track.w, track.h, det.w, det.h, 1.0) * 0.8
                if iou < 0.15 and distance > max_distance:
                    continue
                score = iou + max(0.0, 1.0 - distance / max_distance) * 0.25
                pairs.append((score, track_id, det_index))

        pairs.sort(reverse=True)
        used_tracks: set[int] = set()
        used_detections: set[int] = set()

        for _, track_id, det_index in pairs:
            if track_id in used_tracks or det_index in used_detections:
                continue
            track = active[track_id]
            det = detections[det_index]
            # EMA ringan supaya box tidak ikut jitter deteksi.
            alpha = max(0.2, min(0.9, float(alpha)))
            track.x = alpha * det.x + (1.0 - alpha) * track.x
            track.y = alpha * det.y + (1.0 - alpha) * track.y
            track.w = alpha * det.w + (1.0 - alpha) * track.w
            track.h = alpha * det.h + (1.0 - alpha) * track.h
            track.score = alpha * det.score + (1.0 - alpha) * track.score
            track.hits += 1
            track.misses = 0
            track.last_seen = now
            track.remember()
            used_tracks.add(track_id)
            used_detections.add(det_index)

        for track_id, track in active.items():
            if track_id not in used_tracks:
                track.misses += 1

        for det_index, det in enumerate(detections):
            if det_index in used_detections:
                continue
            track = _FaceTrack(
                track_id=next_id,
                x=det.x,
                y=det.y,
                w=det.w,
                h=det.h,
                score=det.score,
                last_seen=now,
            )
            track.remember()
            active[next_id] = track
            all_tracks[next_id] = track
            next_id += 1

        # Track yang sudah lama hilang tidak boleh menangani deteksi baru,
        # tetapi objeknya tetap disimpan karena observations-nya mungkin
        # masih dipakai untuk membangun jalur crop.
        active = {
            track_id: track
            for track_id, track in active.items()
            if track.misses <= max_missed
        }
        return active, next_id


    def _choose_primary(
        self,
        active: Dict[int, _FaceTrack],
        all_tracks: Dict[int, _FaceTrack],
        state: _SubjectState,
        now: float,
        src_w: int,
        src_h: int,
        lost_grace: float = 0.8,
        switch_hold: int = 5,
    ) -> Optional[_FaceTrack]:
        """Pilih subjek utama dengan lock/hysteresis, bukan wajah terbesar per frame."""
        candidates = [
            track
            for track in active.values()
            if track.hits >= 2 and abs(track.last_seen - now) < 1e-6
        ]
        if not candidates:
            if (
                state.primary_id is not None
                and now - state.last_primary_seen <= lost_grace
            ):
                return all_tracks.get(state.primary_id)
            state.primary_id = None
            state.challenger_id = None
            state.challenger_count = 0
            return None

        if state.primary_id is None or state.primary_id not in all_tracks:
            chosen = max(
                candidates,
                key=lambda track: self._track_strength(track, src_w, src_h),
            )
            state.primary_id = chosen.track_id
            state.last_primary_seen = now
            state.challenger_id = None
            state.challenger_count = 0
            return chosen

        current = all_tracks.get(state.primary_id)
        if current is None:
            state.primary_id = None
            return self._choose_primary(
                active, all_tracks, state, now, src_w, src_h, lost_grace, switch_hold
            )

        current_active = any(
            track.track_id == current.track_id for track in candidates
        )
        if not current_active:
            if now - state.last_primary_seen <= lost_grace:
                return current
            chosen = max(
                candidates,
                key=lambda track: self._track_strength(track, src_w, src_h),
            )
            state.primary_id = chosen.track_id
            state.last_primary_seen = now
            state.challenger_id = None
            state.challenger_count = 0
            return chosen

        others = [track for track in candidates if track.track_id != current.track_id]
        if not others:
            state.challenger_id = None
            state.challenger_count = 0
            state.last_primary_seen = now
            return current

        challenger = max(
            others, key=lambda track: self._track_strength(track, src_w, src_h)
        )
        current_strength = self._track_strength(current, src_w, src_h)
        challenger_strength = self._track_strength(challenger, src_w, src_h)

        if challenger_strength > current_strength * 1.25:
            if state.challenger_id == challenger.track_id:
                state.challenger_count += 1
            else:
                state.challenger_id = challenger.track_id
                state.challenger_count = 1
            if state.challenger_count >= switch_hold:
                state.primary_id = challenger.track_id
                state.last_primary_seen = now
                state.challenger_id = None
                state.challenger_count = 0
                return challenger
        else:
            state.challenger_id = None
            state.challenger_count = 0

        state.last_primary_seen = now
        return current


    def _choose_split_pair(
        self,
        active: Dict[int, _FaceTrack],
        primary: Optional[_FaceTrack],
        src_w: int,
        src_h: int,
        now: float = 0.0,
    ) -> Optional[Tuple[int, int]]:
        """Kembalikan pasangan track untuk split atas/bawah bila cukup jauh."""
        candidates = [
            track
            for track in active.values()
            if track.hits >= 2
            and track.score >= 0.55
            and abs(track.last_seen - now) < 1e-6
        ]
        if len(candidates) < 2:
            return None

        if primary is not None and any(
            track.track_id == primary.track_id for track in candidates
        ):
            first = primary
            others = [
                track for track in candidates if track.track_id != primary.track_id
            ]
            second = max(
                others,
                key=lambda track: self._track_strength(track, src_w, src_h),
            )
        else:
            ordered = sorted(
                candidates,
                key=lambda track: self._track_strength(track, src_w, src_h),
                reverse=True,
            )
            first, second = ordered[0], ordered[1]

        # Kalau wajah terlalu berdekatan, satu crop masih cukup.
        if abs(first.cx - second.cx) < 0.32 * src_w:
            return None
        # Urutkan ID agar pair_counts stabil walau status primary berganti.
        first_id, second_id = sorted((first.track_id, second.track_id))
        result: Tuple[int, int] = (int(first_id), int(second_id))
        return result


    @staticmethod
    def _track_samples(
        track: _FaceTrack,
        duration: float,
        src_w: int,
        src_h: int,
        win_w: float,
        win_h: float,
    ) -> List[Tuple[float, float, float, float, float]]:
        """Ubah observations track menjadi sample crop (koordinat sumber)."""
        center_x = min(max(0.0, src_w / 2.0 - win_w / 2.0), src_w - win_w)
        center_y = min(max(0.0, src_h / 2.0 - win_h / 2.0), src_h - win_h)

        observations = sorted(track.observations, key=lambda item: item[0])
        if not observations:
            return [(0.0, round(center_x), round(center_y), win_w, win_h)]

        samples: List[Tuple[float, float, float, float, float]] = []
        first_t = observations[0][0]
        if first_t > 0.35:
            # Jangan mulai dengan crop menempel ke wajah; beri transisi halus
            # dari tengah frame menuju subjek.
            samples.append((0.0, round(center_x), round(center_y), win_w, win_h))

        last_x, last_y = center_x, center_y
        for t_rel, cx, cy, _, _, _ in observations:
            x = min(max(0.0, cx - win_w / 2.0), src_w - win_w)
            y = min(max(0.0, cy - win_h / 2.0), src_h - win_h)
            last_x, last_y = x, y
            samples.append((float(t_rel), round(x), round(y), win_w, win_h))

        last_t = observations[-1][0]
        if last_t < duration - 0.15:
            # Wajah hilang: tahan posisi sebentar, lalu kembali ke tengah.
            samples.append(
                (
                    min(duration, last_t + 0.5),
                    round(last_x),
                    round(last_y),
                    win_w,
                    win_h,
                )
            )
            samples.append(
                (
                    min(duration, last_t + 1.0),
                    round(center_x),
                    round(center_y),
                    win_w,
                    win_h,
                )
            )

        return samples


    def _analyze_reframe(
        self,
        input_path: str,
        start_time: float,
        duration: float,
        aspect_ratio: str,
        config: Any,
        smoothing: float = 0.35,
        split_screen: bool = True,
        output_fps: int = 30,
    ) -> _SpeakerCropPlan:
        """
        Pipeline analisis AI: sampling -> deteksi -> tracking -> momen -> kamera.

        Tidak menulis video apa pun. Hasil dikembalikan sebagai keyframe kamera
        per frame output plus laporan JSON yang bisa diaudit.
        """
        import cv2
        import numpy as np

        plan = _SpeakerCropPlan(split=False)
        src_w, src_h = self._probe_dimensions(input_path)
        if src_w <= 0 or src_h <= 0:
            plan.analysis = {"error": "unreadable_video", "input": input_path}
            return plan

        target_ratio = self._ratio_value(aspect_ratio)
        fps = max(1, int(output_fps))
        analysis_fps = float(getattr(config, "analysis_fps", 8.0) or 8.0)
        max_side = int(getattr(config, "analysis_max_side", 960) or 960)
        scale = min(1.0, max_side / float(max(src_w, src_h)))
        small_w = max(2, int(round(src_w * scale)) // 2 * 2)
        small_h = max(2, int(round(src_h * scale)) // 2 * 2)

        person_detector = get_person_detector(
            float(getattr(config, "detection_confidence", 0.35) or 0.35),
            prefer_cuda=bool(getattr(config, "prefer_cuda", True)),
        )
        face_detector = get_face_detector(
            small_w, small_h, float(getattr(config, "face_confidence", 0.62) or 0.62)
        )
        tracker = ByteTrackLite(
            high_threshold=float(getattr(config, "detection_confidence", 0.35) or 0.35),
            low_threshold=float(getattr(config, "tracking_confidence", 0.25) or 0.25),
            max_missed=int(getattr(config, "track_max_missed", 12) or 12),
            min_hits=int(getattr(config, "track_min_hits", 3) or 3),
        )

        samples: List[Tuple[float, Optional[int], float, float]] = []
        features = []
        primary_id: Optional[int] = None
        primary_streak = 0
        last_scene_time = -1e9
        prev_small = None
        cut_threshold = float(getattr(config, "scene_cut_threshold", 0.55) or 0.55)
        hold = float(getattr(config, "primary_switch_hold", 1.5) or 1.5)
        min_area = float(getattr(config, "person_min_area_ratio", 0.010) or 0.010)
        edge_margin = float(getattr(config, "edge_margin", 0.10) or 0.10)

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            plan.analysis = {"error": "cannot_open_video", "input": input_path}
            return plan
        try:
            step = 1.0 / max(0.5, analysis_fps)
            times: List[float] = []
            cursor = 0.0
            while cursor < duration:
                times.append(round(cursor, 4))
                cursor += step
            for sample_index, offset in enumerate(times):
                cap.set(cv2.CAP_PROP_POS_MSEC, (start_time + offset) * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                if (frame.shape[1], frame.shape[0]) != (small_w, small_h):
                    small = cv2.resize(frame, (small_w, small_h), interpolation=cv2.INTER_AREA)
                else:
                    small = frame
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                frame_diff = 0.0
                if prev_small is not None:
                    diff = cv2.absdiff(gray, prev_small)
                    frame_diff = float(np.mean(diff)) / 255.0
                scene_cut = False
                if prev_small is not None and frame_diff >= cut_threshold:
                    if offset - last_scene_time > 0.5:
                        scene_cut = True
                        last_scene_time = offset
                        tracker.reset()
                        primary_id = None
                prev_small = gray

                frame_area = float(small_w * small_h)
                raw = person_detector.detect(small)
                detections = []
                for det in raw:
                    if det.area / frame_area < min_area:
                        continue
                    inv = 1.0 / max(1e-6, scale)
                    detections.append(
                        type(det)(
                            det.x * inv, det.y * inv, det.w * inv, det.h * inv,
                            det.score, det.class_id,
                        )
                    )
                tracks = tracker.update(detections, sample_index)
                faces = face_detector.detect(small) if face_detector.available else []
                faces_full = [
                    type(face)(
                        face.x / max(1e-6, scale), face.y / max(1e-6, scale),
                        face.w / max(1e-6, scale), face.h / max(1e-6, scale),
                        face.score, face.class_id,
                    )
                    for face in faces
                ]

                visible = [trk for trk in tracks if trk.misses == 0]
                chosen = tracker.get(primary_id)
                best = None
                best_score = -1.0
                for trk in visible:
                    score = track_strength(trk, src_w, src_h, tracker.min_hits)
                    if trk.track_id == primary_id:
                        score += 0.15  # hysteresis: jangan berpindah tanpa alasan
                    if score > best_score:
                        best, best_score = trk, score
                if chosen is not None and chosen.track_id == primary_id and chosen.misses > 0:
                    best = chosen
                if best is not None:
                    if best.track_id != primary_id:
                        primary_streak += 1
                        if primary_streak >= max(1, int(hold * analysis_fps)):
                            primary_id = best.track_id
                            primary_streak = 0
                    else:
                        primary_streak = 0
                elif chosen is None:
                    primary_id = None

                primary_track = tracker.get(primary_id)
                feat = extract_features(
                    time=offset,
                    frame_index=sample_index,
                    tracks=visible,
                    faces=faces_full,
                    src_w=src_w,
                    src_h=src_h,
                    primary=primary_track if primary_track and primary_track.misses == 0 else None,
                    scene_cut=scene_cut,
                    frame_diff=frame_diff,
                    edge_margin=edge_margin,
                )
                features.append(feat)
                if primary_track is not None:
                    samples.append(
                        (offset, primary_track.track_id, primary_track.cx, primary_track.cy)
                    )
        finally:
            cap.release()

        engine = MomentDetectionEngine(config)
        moment_result = engine.detect(features)
        trajectory = build_trajectory(
            config=config,
            moments=moment_result.moments,
            samples=samples,
            duration=float(duration),
            src_w=src_w,
            src_h=src_h,
            target_ratio=target_ratio,
            output_fps=fps,
        )
        plan.keyframes = trajectory.as_tuples()
        plan.has_zoom = trajectory.has_zoom
        plan.split = False
        plan.analysis = build_report(
            config=config,
            duration=float(duration),
            features=features,
            moment_result=moment_result,
            trajectory=trajectory,
            detector_info={
                "person_backend": person_detector.backend,
                "person_providers": list(person_detector.providers),
                "face_backend": face_detector.backend,
                "analysis_size": [small_w, small_h],
                "source_size": [src_w, src_h],
            },
            extra={
                "aspect_ratio": aspect_ratio,
                "output_fps": fps,
                "crop_formula": "crop=w=min(iw,ih*ratio)/zoom:h=min(ih,iw/ratio)/zoom",
            },
        )
        logger.info(
            "Reframe AI: %s samples=%d persons=%d moments=%d zoom_events=%d backend=%s",
            Path(input_path).name,
            len(features),
            plan.analysis.get("detected_persons", 0),
            plan.analysis.get("selected_moments", 0),
            plan.analysis.get("zoom_events", 0),
            person_detector.backend,
        )
        return plan

    def _reframe_analyze_sync(
        self,
        input_path: str,
        start_time: float,
        duration: float,
        aspect_ratio: str,
        config: Any,
        smoothing: float = 0.35,
        split_screen: bool = True,
        output_fps: int = 30,
    ) -> _SpeakerCropPlan:
        """Analisis AI moment-based (dipanggil di executor, blocking)."""
        plan = _SpeakerCropPlan(split=False)
        try:
            plan = self._analyze_reframe(
                input_path,
                start_time,
                duration,
                aspect_ratio,
                config,
                smoothing,
                split_screen,
                output_fps,
            )
        except Exception as exc:  # pragma: no cover - tergantung media
            logger.warning("Analisis reframe AI gagal (%s); fallback face-only", exc)
            return plan
        if plan.keyframes or plan.primary:
            return plan
        logger.info("Analisis AI tidak menghasilkan subjek; fallback face-only")
        legacy = self._speaker_track_sync(
            input_path,
            start_time,
            duration,
            aspect_ratio,
            float(getattr(config, "maximum_zoom", 1.0) or 1.0),
            float(getattr(config, "analysis_fps", 8.0) or 8.0),
            smoothing,
            split_screen,
        )
        legacy.analysis = plan.analysis
        return legacy

    def _speaker_track_sync(
        self,
        input_path: str,
        start_time: float,
        duration: float,
        aspect_ratio: str,
        zoom: float,
        sample_fps: float,
        smooth: float,
        split_screen: bool = True,
    ) -> _SpeakerCropPlan:
        """Jalur lama (face-only): dipakai hanya bila analisis AI tidak tersedia.

        Deteksi + track wajah, lalu bangun jalur crop utama dan pasangan split.

        Deteksi berjalan pada frame yang diperkecil (maksimal 960 px) dengan
        sample 6-10 fps. Pemilihan subjek memakai track ID + hysteresis, bukan
        wajah terbesar per sample. Bila dua wajah stabil dan berjauhan, plan
        menyertakan jalur kedua untuk split atas/bawah.
        """
        import cv2

        num, den = aspect_ratio.replace(" ", "").split(":", 1)
        target_ratio = float(num) / float(den)
        zoom = max(1.0, float(zoom or 1.0))

        capture = cv2.VideoCapture(input_path)
        if not capture.isOpened():
            return _SpeakerCropPlan()

        src_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        src_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
        if src_w <= 0 or src_h <= 0:
            capture.release()
            return _SpeakerCropPlan()

        # Deteksi pada resolusi lebih kecil: lebih cepat dan false positive
        # wajah kecil/background berkurang. Koordinat dikembalikan ke sumber.
        detect_scale = min(1.0, 960.0 / max(src_w, src_h))
        det_w = max(2, int(round(src_w * detect_scale)) & ~1)
        det_h = max(2, int(round(src_h * detect_scale)) & ~1)
        detector = self._face_detector(det_w, det_h)
        if detector is None:
            capture.release()
            return _SpeakerCropPlan()
        detector.setInputSize((det_w, det_h))

        # Panel split atas/bawah memiliki rasio 2x rasio output. Untuk 9:16
        # panel menjadi 9:8 (1080x960), sehingga crop tidak ditarik/distorsi.
        normal_win = self._crop_window(src_w, src_h, target_ratio, zoom)
        split_ratio = target_ratio * 2.0
        split_win = self._crop_window(src_w, src_h, split_ratio, zoom)

        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_time) * 1000.0)
        step = max(1, int(round(fps / max(0.5, float(sample_fps or 8.0)))))
        total_frames = int(duration * fps)

        all_tracks: Dict[int, _FaceTrack] = {}
        active: Dict[int, _FaceTrack] = {}
        state = _SubjectState()
        next_id = 1
        primary_ids: List[int] = []
        pair_counts: Dict[Tuple[int, int], int] = {}
        sample_count = 0
        prev_gray = None
        tracker_alpha = max(0.35, min(0.85, 0.5 + 0.4 * float(smooth)))
        alive = True
        frame_index = 0

        while alive and frame_index <= total_frames:
            alive, frame = capture.read()
            if not alive or frame is None:
                break
            if frame_index % step == 0:
                small = cv2.resize(
                    frame, (det_w, det_h), interpolation=cv2.INTER_AREA
                )
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                # Scene cut sederhana: reset track supaya crop tidak meluncur
                # dari subjek scene lama ke subjek scene baru.
                if prev_gray is not None:
                    diff = float(cv2.mean(cv2.absdiff(gray, prev_gray))[0]) / 255.0
                    if diff > 0.35:
                        active.clear()
                        state = _SubjectState()
                        # Subjek setelah cut bisa berbeda; jangan biarkan
                        # track scene lama mendominasi pemilihan seluruh klip.
                        primary_ids.clear()
                        pair_counts.clear()
                prev_gray = gray

                # YuNet: faces = Nx15 [x, y, w, h, 5 landmark (x,y), score]
                _, faces = detector.detect(small)
                detections: List[_FaceDetection] = []
                if faces is not None:
                    scale_x = src_w / float(det_w)
                    scale_y = src_h / float(det_h)
                    min_area = max(1.0, src_w * src_h * 0.0008)
                    for box in faces:
                        score = float(box[-1])
                        if score < 0.62:
                            continue
                        fx = float(box[0]) * scale_x
                        fy = float(box[1]) * scale_y
                        fw = float(box[2]) * scale_x
                        fh = float(box[3]) * scale_y
                        if fw < 2.0 or fh < 2.0 or fw * fh < min_area:
                            continue
                        detections.append(
                            _FaceDetection(
                                x=max(0.0, min(fx, src_w - 1.0)),
                                y=max(0.0, min(fy, src_h - 1.0)),
                                w=min(fw, src_w - max(0.0, fx)),
                                h=min(fh, src_h - max(0.0, fy)),
                                score=score,
                            )
                        )

                now = frame_index / fps
                active, next_id = self._update_face_tracks(
                    active,
                    all_tracks,
                    detections,
                    now,
                    next_id,
                    alpha=tracker_alpha,
                )
                primary = self._choose_primary(
                    active, all_tracks, state, now, src_w, src_h
                )
                if primary is not None:
                    primary_ids.append(primary.track_id)
                pair = self._choose_split_pair(
                    active, primary, src_w, src_h, now
                )
                if pair is not None:
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
                sample_count += 1
            frame_index += 1

        capture.release()
        if sample_count == 0 or not all_tracks:
            return _SpeakerCropPlan()

        split_pair: Optional[Tuple[int, int]] = None
        if split_screen and pair_counts and target_ratio < 1.0:
            pair, count = max(pair_counts.items(), key=lambda item: item[1])
            # Split hanya kalau dua orang berjauhan cukup lama (>=50% klip
            # dan minimal 8 sample), bukan karena satu frame kebetulan.
            min_split = max(8, int(math.ceil(sample_count * 0.50)))
            if count >= min_split:
                split_pair = pair

        if split_pair is not None:
            first = all_tracks.get(split_pair[0])
            second = all_tracks.get(split_pair[1])
            if first is not None and second is not None:
                # Panel atas = subjek yang lebih kiri, panel bawah = kanan.
                ordered = sorted((first, second), key=lambda track: track.cx)
                return _SpeakerCropPlan(
                    primary=self._track_samples(
                        ordered[0], duration, src_w, src_h, *split_win
                    ),
                    secondary=self._track_samples(
                        ordered[1], duration, src_w, src_h, *split_win
                    ),
                    split=True,
                )

        if primary_ids:
            primary_id = Counter(primary_ids).most_common(1)[0][0]
        else:
            primary_id = max(all_tracks, key=lambda key: all_tracks[key].hits)
        primary_track = all_tracks.get(primary_id)
        if primary_track is None:
            return _SpeakerCropPlan()
        return _SpeakerCropPlan(
            primary=self._track_samples(
                primary_track, duration, src_w, src_h, *normal_win
            )
        )

    @staticmethod
    def _stabilize_zoom_track(
        keyframes: List[Tuple[float, float, float, float, float]],
        window: int = 5,
    ) -> List[Tuple[float, float, float, float, float]]:
        """
        Rapikan keyframe kamera sebelum render.

        x/y di-smooth dua arah (simetris, tanpa lag) lalu dimasukkan ke
        `_stabilize_track_frames` untuk dead zone + batas kecepatan.
        `w`/`h` TIDAK ikut di-smooth di sini karena zoom sudah punya easing
        sendiri; hanya nilai genap + keyframe redundan yang dibuang.
        """
        if not keyframes:
            return []
        smoothed = VideoProcessor._stabilize_track_frames(list(keyframes), window)
        if not smoothed:
            return []

        def snap(value: float) -> float:
            number = int(round(value))
            return float(number - number % 2) if number >= 2 else 2.0

        out: List[Tuple[float, float, float, float, float]] = []
        for index, (t_rel, x, y, win_w, win_h) in enumerate(smoothed):
            size_w, size_h = snap(win_w), snap(win_h)
            item = (float(t_rel), float(int(round(x))), float(int(round(y))), size_w, size_h)
            if index == 0 or item[1:] != out[-1][1:]:
                out.append(item)
            else:
                # posisi & ukuran sama: cukup simpan timestamp terakhir
                out[-1] = item
        return out

    @staticmethod
    def _interpolate_track_frames(
        track: List[Tuple[float, float, float, float, float]],
        duration: float,
        output_fps: int,
    ) -> List[Tuple[float, float, float, float, float]]:
        """Interpolasi sampel deteksi ke posisi crop SETIAP frame output.

        Deteksi boleh berjalan 2.5-10 fps, tetapi filter `crop` harus menerima
        perubahan posisi per frame. Tanpa interpolasi, ffmpeg diam selama
        beberapa frame lalu melompat ke nilai sample berikutnya (judder).
        """
        if not track:
            return []

        fps = max(1, int(output_fps or 30))
        total_frames = max(1, int(round(max(0.0, float(duration)) * fps)))

        # Sample bisa datang dari frame yang sama (mis. rounding timestamp);
        # np.interp mensyaratkan xp menaik dan unik.
        ordered = sorted(track, key=lambda item: item[0])
        samples: List[Tuple[float, float, float, float, float]] = []
        for item in ordered:
            if samples and abs(item[0] - samples[-1][0]) < 1e-6:
                samples[-1] = item
            else:
                samples.append(item)

        if len(samples) == 1:
            _, x, y, win_w, win_h = samples[0]
            return [
                (frame_index / fps, x, y, win_w, win_h)
                for frame_index in range(total_frames)
            ]

        import numpy as np

        sample_times = [item[0] for item in samples]
        sample_x = [item[1] for item in samples]
        sample_y = [item[2] for item in samples]
        frame_times = np.arange(total_frames, dtype=np.float64) / fps
        xs = np.interp(frame_times, sample_times, sample_x)
        ys = np.interp(frame_times, sample_times, sample_y)
        # Ukuran jendela ikut diinterpolasi supaya zoom bergerak halus per
        # frame, bukan melompat di batas dua sample.
        ws = np.interp(frame_times, sample_times, [item[3] for item in samples])
        hs = np.interp(frame_times, sample_times, [item[4] for item in samples])

        return [
            (
                float(frame_times[index]),
                float(int(round(float(xs[index])))),
                float(int(round(float(ys[index])))),
                float(int(round(float(ws[index])))),
                float(int(round(float(hs[index])))),
            )
            for index in range(total_frames)
        ]

    @staticmethod
    def _stabilize_track_frames(
        track: List[Tuple[float, float, float, float, float]],
        window: int = 5,
    ) -> List[Tuple[float, float, float, float, float]]:
        """Smoothing dua arah + dead zone + batas kecepatan per frame.

        Semua sample sudah tersedia sebelum render, jadi smoothing bisa
        simetris (tidak menimbulkan lag seperti EMA satu arah).
        """
        if not track:
            return []
        if len(track) < 3 or window < 3:
            return track

        import numpy as np

        window = window if window % 2 == 1 else window + 1
        times = [item[0] for item in track]
        xs = np.array([item[1] for item in track], dtype=np.float64)
        ys = np.array([item[2] for item in track], dtype=np.float64)
        # `w`/`h` HARUS mengikuti setiap keyframe: di sinilah zoom diwujudkan.
        # Membekukannya ke nilai frame pertama (perilaku lama) membuat seluruh
        # animasi zoom hilang walau trajectory & report sudah benar.
        ws = np.array([item[3] for item in track], dtype=np.float64)
        hs = np.array([item[4] for item in track], dtype=np.float64)
        win_w = float(track[0][3])
        win_h = float(track[0][4])

        pad = window // 2
        kernel = np.ones(window, dtype=np.float64) / window
        xs = np.convolve(np.pad(xs, (pad, pad), mode="edge"), kernel, mode="valid")
        ys = np.convolve(np.pad(ys, (pad, pad), mode="edge"), kernel, mode="valid")

        dead_x = max(1.0, win_w * 0.02)
        dead_y = max(1.0, win_h * 0.02)
        max_step_x = max(2.0, win_w * 0.006)
        max_step_y = max(2.0, win_h * 0.006)

        def limit_axis(target: float, current: float, dead: float, max_step: float) -> float:
            delta = target - current
            if abs(delta) <= dead:
                return current
            step = delta - math.copysign(dead, delta)
            step = max(-max_step, min(max_step, step))
            return current + step

        out = [track[0]]
        for index in range(1, len(track)):
            x = limit_axis(float(xs[index]), out[-1][1], dead_x, max_step_x)
            y = limit_axis(float(ys[index]), out[-1][2], dead_y, max_step_y)
            out.append(
                (
                    times[index],
                    float(int(round(x))),
                    float(int(round(y))),
                    float(int(round(float(ws[index])))),
                    float(int(round(float(hs[index])))),
                )
            )
        return out

    @staticmethod
    def _write_crop_commands(
        cmd_path: str,
        track: List[Tuple[float, float, float, float, float]],
        target: str = "crop",
        include_size: bool = False,
    ) -> None:
        """Tulis command sendcmd per frame untuk filter crop biasa/named."""
        commands: List[str] = []
        previous: Optional[Tuple[float, float]] = None
        for t_rel, x, y, win_w, win_h in track:
            commands.append(f"{t_rel:.3f} {target} x {x:.0f};")
            commands.append(f"{t_rel:.3f} {target} y {y:.0f};")
            if include_size:
                size = (round(float(win_w)), round(float(win_h)))
                if previous is None or size != previous:
                    commands.append(f"{t_rel:.3f} {target} w {size[0]:.0f};")
                    commands.append(f"{t_rel:.3f} {target} h {size[1]:.0f};")
                    previous = size
        Path(cmd_path).write_text("\n".join(commands), encoding="utf-8")

    async def _render_tracked_single(
        self,
        input_path: str,
        output_path: str,
        track: List[Tuple[float, float, float, float, float]],
        start_time: float,
        duration: float,
        width: int,
        height: int,
        output_fps: int,
        filter_preset: Optional[str],
    ) -> str:
        _, first_x, first_y, win_w, win_h = track[0]
        cmd_path = str(Path(output_path).with_name(f"track_{uuid4().hex}.cmd"))
        # `w`/`h` dikirim runtime supaya zoom (dan reset ke framing asli)
        # benar-benar berubah di tengah video, bukan hanya posisi x/y.
        self._write_crop_commands(cmd_path, track, target="crop", include_size=True)

        preset_chain = self.filter_chain_for_preset(filter_preset)
        # fps + setpts dulu supaya filter melihat frame output dan timeline
        # sendcmd dimulai dari 0. Tanpa ini, sumber 24/25/60 fps bisa membuat
        # command jatuh di frame yang tidak tepat.
        chain = (
            f"fps={output_fps},setpts=PTS-STARTPTS,"
            f"sendcmd=f={self._escape_filter_path(cmd_path)},"
            f"crop=w={int(win_w)}:h={int(win_h)}:"
            f"x={int(round(first_x))}:y={int(round(first_y))},"
            f"scale={width}:{height}:flags=lanczos,setsar=1"
        )
        if preset_chain:
            chain = f"{chain},{preset_chain}"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-vf", chain,
            *self.video_encode_args(21),
            "-r", str(output_fps),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        finally:
            try:
                os.remove(cmd_path)
            except OSError:
                pass
        return output_path

    async def _render_tracked_split(
        self,
        input_path: str,
        output_path: str,
        top_track: List[Tuple[float, float, float, float, float]],
        bottom_track: List[Tuple[float, float, float, float, float]],
        start_time: float,
        duration: float,
        width: int,
        height: int,
        output_fps: int,
        filter_preset: Optional[str],
    ) -> str:
        """Render dua panel atas/bawah dengan crop path masing-masing."""
        panel_h = max(2, int(height) // 2)
        panel_h -= panel_h % 2
        _, top_x, top_y, top_w, top_h = top_track[0]
        _, bottom_x, bottom_y, bottom_w, bottom_h = bottom_track[0]

        top_cmd = str(Path(output_path).with_name(f"track_top_{uuid4().hex}.cmd"))
        bottom_cmd = str(
            Path(output_path).with_name(f"track_bottom_{uuid4().hex}.cmd")
        )
        self._write_crop_commands(top_cmd, top_track, target="crop@top")
        self._write_crop_commands(bottom_cmd, bottom_track, target="crop@bottom")

        preset_chain = self.filter_chain_for_preset(filter_preset)
        graph = (
            f"[0:v]fps={output_fps},setpts=PTS-STARTPTS,split=2[src_top][src_bottom];"
            f"[src_top]sendcmd=f={self._escape_filter_path(top_cmd)},"
            f"crop@top=w={int(top_w)}:h={int(top_h)}:"
            f"x={int(round(top_x))}:y={int(round(top_y))},"
            f"scale={width}:{panel_h}:flags=lanczos,setsar=1[top];"
            f"[src_bottom]sendcmd=f={self._escape_filter_path(bottom_cmd)},"
            f"crop@bottom=w={int(bottom_w)}:h={int(bottom_h)}:"
            f"x={int(round(bottom_x))}:y={int(round(bottom_y))},"
            f"scale={width}:{panel_h}:flags=lanczos,setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2"
            + (f",{preset_chain}" if preset_chain else "")
            + "[v]"
        )

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-filter_complex", graph,
            "-map", "[v]", "-map", "0:a?",
            *self.video_encode_args(21),
            "-r", str(output_fps),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        finally:
            for path in (top_cmd, bottom_cmd):
                try:
                    os.remove(path)
                except OSError:
                    pass
        return output_path



    async def track_speaker_crop(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        aspect_ratio: str = "9:16",
        zoom: float = 1.0,
        filter_preset: Optional[str] = None,
        sample_fps: float = 8.0,
        smoothing: float = 0.35,
        split_screen: bool = True,
        reframe_options: Optional[Dict[str, Any]] = None,
        analysis_path: Optional[str] = None,
    ) -> str:
        """
        Render klip dengan jendela crop yang MENGIKUTI wajah pembicara.

        Jalur utama sekarang AI moment-based reframing:

            1. analisis (YOLO11n person + YuNet face + ByteTrack-style tracker)
            2. Moment Detection Engine (skor + durasi minimum + cooldown)
            3. virtual camera (zoom state machine + camera follow smooth)
            4. render FFmpeg `sendcmd` + crop runtime w/h

        Zoom hanya terjadi pada momen yang lolos validasi; tanpa momen valid
        framing asli dipertahankan (tidak ada zoom statis sepanjang video).
        Split atas/bawah tetap tersedia dan dipakai bila dua subjek stabil.

        `reframe_options` menerima `editing_options` task (nama lama tetap
        dihormati: `auto_zoom`, `zoom_level`, `auto_zoom_split`).
        """
        options = dict(reframe_options or {})
        config = load_reframe_config(options)
        # Nilai lama dari signature tetap berlaku bila opsi tidak diberikan.
        if not reframe_options:
            legacy: Dict[str, Any] = {}
            if zoom and float(zoom) > 1.0:
                legacy["maximum_zoom"] = float(zoom)
            if sample_fps:
                legacy["analysis_fps"] = float(sample_fps)
            config = load_reframe_config(legacy).sanitized()

        width, height = self._dimensions_for_ratio(aspect_ratio)
        output_fps = max(1, int(settings.OUTPUT_FPS or 30))
        loop = asyncio.get_event_loop()

        plan = await loop.run_in_executor(
            None,
            functools.partial(
                self._reframe_analyze_sync,
                input_path,
                start_time,
                duration,
                aspect_ratio,
                config,
                smoothing,
                split_screen,
                output_fps,
            ),
        )

        if analysis_path and plan.analysis:
            try:
                Path(analysis_path).parent.mkdir(parents=True, exist_ok=True)
                Path(analysis_path).write_text(
                    json.dumps(plan.analysis, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except OSError as exc:
                logger.warning("Gagal menulis analysis report: %s", exc)

        async def fallback() -> str:
            logger.warning("Track wajah kosong; memakai crop tengah: %s", input_path)
            return await self.render_clip(
                input_path, output_path,
                start_time=start_time, duration=duration,
                aspect_ratio=aspect_ratio, filter_preset=filter_preset,
            )

        if not plan.primary and not plan.keyframes:
            return await fallback()

        if plan.keyframes:
            track = self._stabilize_zoom_track(plan.keyframes)
            if not track:
                return await fallback()
            if plan.split and plan.secondary and height > width:
                secondary = self._interpolate_track_frames(
                    plan.secondary, duration, output_fps
                )
                secondary = self._stabilize_track_frames(secondary)
                if secondary:
                    logger.info("Auto zoom split atas/bawah aktif: %s", input_path)
                    return await self._render_tracked_split(
                        input_path,
                        output_path,
                        track,
                        secondary,
                        start_time,
                        duration,
                        width,
                        height,
                        output_fps,
                        filter_preset,
                    )
            return await self._render_tracked_single(
                input_path,
                output_path,
                track,
                start_time,
                duration,
                width,
                height,
                output_fps,
                filter_preset,
            )

        # Jalur lama (face-only) dipertahankan sebagai fallback.
        plan = await loop.run_in_executor(
            None,
            self._speaker_track_sync,
            input_path,
            start_time,
            duration,
            aspect_ratio,
            zoom,
            sample_fps,
            smoothing,
            split_screen,
        )

        if not plan.primary:
            return await fallback()

        primary = self._interpolate_track_frames(
            plan.primary, duration, output_fps
        )
        primary = self._stabilize_track_frames(primary)
        if not primary:
            return await fallback()

        if plan.split and plan.secondary and height > width:
            secondary = self._interpolate_track_frames(
                plan.secondary, duration, output_fps
            )
            secondary = self._stabilize_track_frames(secondary)
            if secondary:
                logger.info(
                    "Auto zoom split atas/bawah aktif: %s", input_path
                )
                return await self._render_tracked_split(
                    input_path,
                    output_path,
                    primary,
                    secondary,
                    start_time,
                    duration,
                    width,
                    height,
                    output_fps,
                    filter_preset,
                )

        return await self._render_tracked_single(
            input_path,
            output_path,
            primary,
            start_time,
            duration,
            width,
            height,
            output_fps,
            filter_preset,
        )

    async def split_clip(
        self,
        input_path: str,
        output_a: str,
        output_b: str,
        at_time: float,
    ) -> tuple[str, str]:
        """
        Potong satu klip jadi dua bagian di detik `at_time` (stream copy, cepat).

        ffmpeg memakai keyframe terdekat sebagai titik potong, jadi hasil bisa
        bergeser < 1 detik — cukup untuk keperluan editing cepat.
        """
        loop = asyncio.get_event_loop()

        part_a = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path, "-t", f"{at_time:.3f}",
            "-c", "copy", "-movflags", "+faststart", output_a,
        ]
        part_b = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", f"{at_time:.3f}", "-i", input_path,
            "-c", "copy", "-movflags", "+faststart", output_b,
        ]

        await loop.run_in_executor(None, self._run_ffmpeg, part_a)
        await loop.run_in_executor(None, self._run_ffmpeg, part_b)
        return output_a, output_b

    async def concat_with_transition(
        self,
        input_paths: List[str],
        output_path: str,
        transition: str = "fade",
        transition_duration: float = 0.4,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """
        Gabungkan beberapa klip dengan transisi opsional.

        transition="none" → sambung lurus (concat_videos). Selain itu memakai
        xfade (video) + acrossfade (audio). Semua input dinormalkan dulu karena
        xfade menuntut resolusi/fps/format audio yang identik.
        """
        if not input_paths:
            raise ValueError("concat_with_transition butuh minimal satu input")
        if len(input_paths) == 1:
            import shutil as _shutil
            _shutil.copyfile(input_paths[0], output_path)
            return output_path
        if (transition or "none").lower() == "none":
            return await self.concat_videos(input_paths, output_path, width, height)

        loop = asyncio.get_event_loop()
        durations: List[float] = []
        for path in input_paths:
            info = await self.get_video_info(path)
            durations.append(float(info.get("duration") or 0))
        if any(d <= 0 for d in durations):
            return await self.concat_videos(input_paths, output_path, width, height)

        fade = max(0.1, min(float(transition_duration), min(durations) / 2))

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]
        for path in input_paths:
            cmd += ["-i", path]

        parts: List[str] = []
        for index in range(len(input_paths)):
            parts.append(
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"fps={settings.OUTPUT_FPS},format=yuv420p[v{index}];"
                f"[{index}:a]aresample=async=1:first_pts=0[a{index}]"
            )

        last_v, last_a = "v0", "a0"
        offset = durations[0] - fade
        for index in range(1, len(input_paths)):
            out_v, out_a = f"vx{index}", f"ax{index}"
            parts.append(
                f"[{last_v}][v{index}]xfade=transition={transition}:"
                f"duration={fade:.3f}:offset={offset:.3f}[{out_v}]"
            )
            parts.append(f"[{last_a}][a{index}]acrossfade=d={fade:.3f}[{out_a}]")
            offset += durations[index] - fade
            last_v, last_a = out_v, out_a

        cmd += [
            "-filter_complex", ";".join(parts),
            "-map", f"[{last_v}]", "-map", f"[{last_a}]",
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            output_path,
        ]

        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def mix_music(
        self,
        input_path: str,
        music_path: str,
        output_path: str,
        volume: float = 0.22,
        ducking: bool = True,
        fade: float = 1.0,
    ) -> str:
        """
        Campur musik latar ke video.

        `ducking=True` memakai sidechaincompress: volume musik otomatis turun
        saat ada suara orang (sidechain = audio asli), jadi narasi tetap jelas.
        Musik di-loop lalu dipotong sesuai durasi video dan diberi fade in/out.
        """
        loop = asyncio.get_event_loop()
        info = await self.get_video_info(input_path)
        duration = float(info.get("duration") or 0) or 1.0
        fade = max(0.0, min(float(fade), duration / 2))
        vol = max(0.0, min(1.0, float(volume)))

        music_chain = (
            f"[1:a]volume={vol:.3f},atrim=0:{duration:.3f},asetpts=N/SR/TB,"
            f"afade=t=in:st=0:d={fade:.2f},"
            f"afade=t=out:st={max(0.0, duration - fade):.2f}:d={fade:.2f}[mus]"
        )

        if ducking:
            filter_complex = (
                f"[0:a]asplit=2[sp][sc];"
                f"{music_chain};"
                f"[mus][sc]sidechaincompress=threshold=0.05:ratio=6:attack=15:release=350[musd];"
                f"[sp][musd]amix=inputs=2:duration=first:dropout_transition=0,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11[a]"
            )
        else:
            filter_complex = (
                f"{music_chain};"
                f"[0:a][mus]amix=inputs=2:duration=first:dropout_transition=0,"
                f"loudnorm=I=-14:TP=-1.5:LRA=11[a]"
            )

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-stream_loop", "-1", "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    @staticmethod
    def _escape_filter_path(path: str) -> str:
        """Escape path agar aman sebagai opsi filter ffmpeg."""
        text = str(path).replace("\\", "/")
        text = text.replace(":", r"\:").replace("'", r"\'")
        return f"'{text}'"

    async def overlay_image(
        self,
        input_path: str,
        image_path: str,
        output_path: str,
        position: str = "bottom-right",
        scale: float = 0.16,
        opacity: float = 0.85,
        start: Optional[float] = None,
        end: Optional[float] = None,
        margin: int = 24,
    ) -> str:
        """
        Tempel PNG (logo/watermark/sticker) di atas video.

        `scale` = lebar watermark relatif lebar video (0.16 = 16%).
        `start`/`end` membatasi kapan watermark tampil (detik).
        """
        positions = {
            "top-left": f"{margin}:{margin}",
            "top-right": f"main_w-overlay_w-{margin}:{margin}",
            "bottom-left": f"{margin}:main_h-overlay_h-{margin}",
            "bottom-right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
            "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
        }
        pos = positions.get((position or "bottom-right").lower(), positions["bottom-right"])

        enable = ""
        if start is not None and end is not None:
            enable = f":enable='between(t,{float(start)},{float(end)})'"
        elif start is not None:
            enable = f":enable='gte(t,{float(start)})'"
        elif end is not None:
            enable = f":enable='lte(t,{float(end)})'"

        alpha = max(0.0, min(1.0, float(opacity)))

        # Lebar logo dihitung langsung dalam piksel dari ukuran video (dibaca via
        # ffprobe). Ini lebih deterministik daripada scale2ref: tidak ada
        # ketergantungan urutan label stream yang mudah tertukar.
        info = await self.get_video_info(input_path)
        target_w = max(24, int(round(float(info.get("width") or 1080) * float(scale))))
        target_w += target_w % 2  # lebar genap agar aman untuk yuv420p

        filter_complex = (
            f"[1:v]format=rgba,scale={target_w}:-2,"
            f"colorchannelmixer=aa={alpha}[wm];"
            f"[0:v][wm]overlay={pos}{enable}[v]"
        )

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            *self.video_encode_args(21),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    # =====================================================================
    # Ken Burns / manual pan
    # =====================================================================
    @staticmethod
    def ken_burns_filter_chain(
        width: int,
        height: int,
        duration: float,
        output_fps: int,
        zoom: float = 1.12,
        direction: str = "zoom-in",
    ) -> str:
        """Bangun filter ``zoompan`` untuk Ken Burns/manual pan.

        Arah yang didukung: zoom-in, zoom-out, left-right, right-left,
        top-bottom, bottom-top, center. Fungsi murni supaya bisa diuji tanpa
        menjalankan ffmpeg.
        """
        total = max(1, int(round(float(duration or 1) * max(1, int(output_fps)))))
        zmax = max(1.01, min(3.0, float(zoom or 1.12)))
        pan = (direction or "zoom-in").strip().lower()
        if pan in {"in", "zoom-in", "kenburns-in"}:
            z = f"min({zmax:.4f},1+({zmax - 1:.4f})*on/{total})"
        elif pan in {"out", "zoom-out", "kenburns-out"}:
            z = f"max(1,{zmax:.4f}-({zmax - 1:.4f})*on/{total})"
        else:
            z = f"{zmax:.4f}"

        center_x = "(iw-iw/zoom)/2"
        center_y = "(ih-ih/zoom)/2"
        if pan == "left-right":
            x, y = f"(iw-iw/zoom)*on/{total}", center_y
        elif pan == "right-left":
            x, y = f"(iw-iw/zoom)*(1-on/{total})", center_y
        elif pan == "top-bottom":
            x, y = center_x, f"(ih-ih/zoom)*on/{total}"
        elif pan == "bottom-top":
            x, y = center_x, f"(ih-ih/zoom)*(1-on/{total})"
        else:
            x, y = center_x, center_y

        return (
            f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=increase,"
            f"crop={int(width)}:{int(height)},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:"
            f"s={int(width)}x{int(height)}:fps={int(output_fps)},setsar=1"
        )

    async def render_ken_burns(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        aspect_ratio: str = "9:16",
        zoom: float = 1.12,
        direction: str = "zoom-in",
        filter_preset: Optional[str] = None,
    ) -> str:
        """Render klip dengan gerakan kamera manual (Ken Burns/pan)."""
        width, height = self._dimensions_for_ratio(aspect_ratio)
        output_fps = max(1, int(settings.OUTPUT_FPS or 30))
        chain = self.ken_burns_filter_chain(
            width, height, duration, output_fps, zoom=zoom, direction=direction
        )
        preset_chain = self.filter_chain_for_preset(filter_preset)
        if preset_chain:
            chain = f"{chain},{preset_chain}"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-vf", chain,
            "-r", str(output_fps),
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def overlay_video(
        self,
        input_path: str,
        overlay_path: str,
        output_path: str,
        position: str = "bottom-right",
        scale: float = 0.32,
        opacity: float = 1.0,
        start: Optional[float] = None,
        end: Optional[float] = None,
        margin: int = 24,
    ) -> str:
        """Tempel video/gambar B-roll di atas klip.

        Video overlay di-loop bila lebih pendek; gambar memakai ``-loop 1``.
        ``scale`` adalah lebar overlay relatif lebar video utama.
        """
        info = await self.get_video_info(input_path)
        duration = float(info.get("duration") or 0) or 1.0
        width = int(info.get("width") or 1080)
        positions = {
            "top-left": f"{margin}:{margin}",
            "top-right": f"main_w-overlay_w-{margin}:{margin}",
            "bottom-left": f"{margin}:main_h-overlay_h-{margin}",
            "bottom-right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
            "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
        }
        pos = positions.get((position or "bottom-right").lower(), positions["bottom-right"])
        enable = ""
        if start is not None and end is not None:
            enable = f":enable='between(t,{float(start)},{float(end)})'"
        elif start is not None:
            enable = f":enable='gte(t,{float(start)})'"
        elif end is not None:
            enable = f":enable='lte(t,{float(end)})'"

        target_w = max(24, int(round(width * max(0.05, min(float(scale), 1.0)))))
        target_w += target_w % 2
        alpha = max(0.0, min(1.0, float(opacity)))
        suffix = Path(overlay_path).suffix.lower()
        is_image = suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
        ]
        if is_image:
            cmd += ["-loop", "1", "-framerate", str(max(1, int(settings.OUTPUT_FPS or 30)))]
        else:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", overlay_path]

        filter_complex = (
            f"[1:v]scale={target_w}:-2:force_original_aspect_ratio=decrease,"
            f"format=rgba,colorchannelmixer=aa={alpha}[ov];"
            f"[0:v][ov]overlay={pos}:eof_action=repeat{enable}[v]"
        )
        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "0:a?",
            "-t", f"{duration:.3f}",
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def ensure_audio(self, input_path: str, output_path: str) -> str:
        """Pastikan video punya track audio (tambahkan senyap bila tidak ada)."""
        info = await self.get_video_info(input_path)
        if info.get("has_audio"):
            import shutil as _shutil
            _shutil.copyfile(input_path, output_path)
            return output_path
        duration = float(info.get("duration") or 0) or 1.0
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest", "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-t", f"{duration:.3f}",
            "-movflags", "+faststart",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def mute_audio(self, input_path: str, output_path: str) -> str:
        """Bisukan audio satu segmen tanpa menghapus stream (aman untuk concat)."""
        info = await self.get_video_info(input_path)
        if not info.get("has_audio"):
            return await self.ensure_audio(input_path, output_path)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-af", "volume=0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def trim_video(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        end_time: Optional[float] = None,
        speed: float = 1.0,
        filter_preset: Optional[str] = None,
    ) -> str:
        """Potong klip yang sudah jadi, opsional speed/filter (tanpa crop ulang)."""
        speed = max(0.25, min(4.0, float(speed or 1.0)))
        filters: List[str] = []
        preset_chain = self.filter_chain_for_preset(filter_preset)
        if preset_chain:
            filters.append(preset_chain)
        if speed != 1.0:
            filters.append(f"setpts=PTS/{speed:.4f}")

        audio_filters: List[str] = []
        if speed != 1.0:
            remaining = speed
            while remaining > 2.0:
                audio_filters.append("atempo=2.0")
                remaining /= 2.0
            while remaining < 0.5:
                audio_filters.append("atempo=0.5")
                remaining /= 0.5
            audio_filters.append(f"atempo={remaining:.4f}")

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(max(0.0, float(start_time))),
            "-i", input_path,
        ]
        if end_time is not None and float(end_time) > float(start_time):
            cmd += ["-t", str(float(end_time) - float(start_time))]
        if filters:
            cmd += ["-vf", ",".join(filters)]
        if audio_filters:
            cmd += ["-af", ",".join(audio_filters)]
        cmd += [
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            output_path,
        ]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def enhance_audio(
        self,
        input_path: str,
        output_path: str,
        denoise: bool = True,
        normalize: bool = True,
        highpass_hz: int = 80,
    ) -> str:
        """
        Perbaiki audio: buang noise (afftdn), potong frekuensi rendah (highpass),
        dan normalisasi kenyaringan ke standar media sosial (loudnorm -14 LUFS).
        """
        filters: List[str] = []
        if denoise:
            filters.append("afftdn=nf=-25")
        if highpass_hz:
            filters.append(f"highpass=f={highpass_hz}")
        if normalize:
            filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")

        if not filters:
            import shutil as _shutil
            _shutil.copyfile(input_path, output_path)
            return output_path

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-af", ",".join(filters),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def concat_videos(
        self,
        input_paths: List[str],
        output_path: str,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """
        Gabungkan beberapa video berurutan (intro + klip + outro) dengan
        menyeragamkan resolusi, fps, dan sampling audio lebih dulu.
        """
        if not input_paths:
            raise ValueError("concat_videos butuh minimal satu input")

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]
        for path in input_paths:
            cmd += ["-i", path]

        parts = []
        for index in range(len(input_paths)):
            parts.append(
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={settings.OUTPUT_FPS}[v{index}];"
                f"[{index}:a]aresample=async=1:first_pts=0[a{index}]"
            )
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(input_paths)))
        filter_complex = ";".join(parts) + f";{concat_inputs}concat=n={len(input_paths)}:v=1:a=1[v][a]"

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def burn_subtitle(
        self,
        input_path: str,
        subtitle_path: str,
        output_path: str,
        style: str = "default",
    ) -> str:
        """
        Bakar subtitle SRT ke video.

        `style` adalah nama preset di CAPTION_STYLES (classic/gold/boxed/neon/
        top/center). Nilainya diteruskan ke libass lewat `force_style`, jadi
        warna, ketebalan garis tepi, kotak latar, dan posisi ikut berubah tanpa
        perlu menulis ulang file SRT.
        """
        vf_filter = f"subtitles=filename={self._escape_filter_path(subtitle_path)}"
        preset = CAPTION_STYLES.get((style or "").strip().lower())
        # File .ass sudah membawa style sendiri (ukuran/posisi/karaoke), jadi
        # force_style tidak boleh menimpanya.
        is_ass = str(subtitle_path).lower().endswith(".ass")
        if preset and not is_ass:
            # force_style berisi koma, jadi harus dibungkus kutip tunggal agar
            # filtergraph tidak menganggapnya pemisah antar-filter.
            force = str(preset["force_style"]).replace("'", "")
            vf_filter += f":force_style='{force}'"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vf", vf_filter,
            *self.video_encode_args(21),
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def compress_video(
        self,
        input_path: str,
        output_path: str,
        crf: int = 23,
    ) -> str:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            *self.video_encode_args(crf, "medium"),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def remove_silence(
        self,
        input_path: str,
        output_path: str,
        min_silence_duration: float = 0.6,
        noise_db: int = -35,
    ) -> str:
        """
        Buang jeda/senyap termasuk di TENGAH klip (jump cuts), video & audio
        tetap sinkron.

        Implementasi lama memakai `silenceremove` + `-c:v copy`: hanya senyap di
        awal yang terpotong, dan video tidak ikut dipotong sehingga audio jadi
        tidak sinkron. Versi ini:
          1. deteksi interval senyap dengan filter `silencedetect`
          2. hitung interval yang dipertahankan (komplemen)
          3. render ulang dengan trim + concat untuk video DAN audio
        """
        loop = asyncio.get_event_loop()
        # capture_output=True wajib: tanpa itu stderr tidak ditangkap sehingga
        # daftar interval senyap selalu kosong dan fungsi ini tidak memotong apa pun.
        probe_runner = functools.partial(subprocess.run, capture_output=True, text=True)
        probe = await loop.run_in_executor(
            None,
            probe_runner,
            [
                "ffmpeg", "-hide_banner", "-nostdin", "-i", input_path,
                "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
                "-f", "null", "-",
            ],
        )
        stderr = probe.stderr or ""

        starts = [float(m) for m in re.findall(r"silence_start:\s*(-?[\d.]+)", stderr)]
        ends = [float(m) for m in re.findall(r"silence_end:\s*(-?[\d.]+)", stderr)]

        info = await self.get_video_info(input_path)
        total = float(info.get("duration") or 0)
        if not total or not starts:
            import shutil as _shutil
            _shutil.copyfile(input_path, output_path)
            return output_path

        silence: List[Tuple[float, float]] = []
        for index, start in enumerate(starts):
            start = max(0.0, start)
            end = ends[index] if len(ends) > index else total
            if end > start:
                silence.append((start, min(end, total)))

        keep: List[Tuple[float, float]] = []
        cursor = 0.0
        for start, end in silence:
            if start - cursor > 0.2:
                keep.append((cursor, start))
            cursor = max(cursor, end)
        if total - cursor > 0.2:
            keep.append((cursor, total))
        if not keep:
            keep = [(0.0, total)]

        parts: List[str] = []
        for index, (start, end) in enumerate(keep):
            parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}];"
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]"
            )
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keep)))
        filter_complex = ";".join(parts) + f";{concat_inputs}concat=n={len(keep)}:v=1:a=1[v][a]"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            *self.video_encode_args(21),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    def _run_ffmpeg(self, cmd: List[str]):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    async def extract_audio(
        self,
        input_path: str,
        output_path: str,
        sample_rate: int = 16000,
    ) -> str:
        """Ekstrak audio mono 16 kHz (format ideal untuk API transkripsi)."""
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-c:a", "libmp3lame", "-q:a", "4",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        return output_path

    async def extract_thumbnail(
        self,
        input_path: str,
        output_path: str,
        at_second: float = 1.0,
    ) -> Optional[str]:
        """Ambil satu frame sebagai thumbnail JPEG (None bila gagal)."""
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(at_second),
            "-i", input_path,
            "-frames:v", "1",
            "-q:v", "3",
            output_path,
        ]

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._run_ffmpeg, cmd)
            return output_path
        except Exception:
            return None

    def _probe_sync(self, cmd: List[str]) -> str:
        """Jalankan ffprobe (sync) dan kembalikan stdout JSON.

        `-v quiet` membuat stderr kosong saat gagal sehingga pesan error tidak
        informatif ("ffprobe gagal:"). Pakai `-v error` dan sertakan path +
        returncode agar kegagalan bisa didiagnosa dari log worker.
        """
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            target = cmd[-1] if cmd else "?"
            detail = (result.stderr or result.stdout or "").strip()
            exists = os.path.exists(target) if isinstance(target, str) else False
            size = os.path.getsize(target) if exists else -1
            raise RuntimeError(
                f"ffprobe gagal (exit {result.returncode}) untuk {target} "
                f"(ada={exists}, ukuran={size} B): {detail[:500] or '(tanpa pesan)'}"
            )
        return result.stdout

    async def get_video_info(self, video_path: str) -> Dict[str, Any]:
        if not os.path.exists(video_path):
            parent = os.path.dirname(video_path) or "."
            try:
                siblings = sorted(os.listdir(parent))[:10]
            except OSError:
                siblings = []
            raise RuntimeError(
                f"file video tidak ditemukan: {video_path} "
                f"(isi folder {parent}: {siblings})"
            )
        cmd = [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", video_path,
        ]
        loop = asyncio.get_event_loop()
        stdout = await loop.run_in_executor(None, self._probe_sync, cmd)

        import json
        data = json.loads(stdout)
        
        duration = float(data.get("format", {}).get("duration", 0))
        width = 0
        height = 0
        has_audio = False
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "audio":
                has_audio = True
            if stream.get("codec_type") == "video" and not width:
                width = stream.get("width", 0)
                height = stream.get("height", 0)

        return {
            "duration": duration,
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}",
            # Unduhan fallback `b*` bisa menghasilkan video tanpa audio; pipeline
            # memakai flag ini supaya tidak gagal membingungkan di transkripsi.
            "has_audio": has_audio,
        }
