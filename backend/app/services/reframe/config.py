"""
Konfigurasi AI Moment-Based Auto Reframing.

Sumber nilai, urutan prioritas (yang terakhir menang):

    1. default dataclass (aman untuk CPU, tanpa zoom agresif)
    2. environment variable (`REFRAME_*` / `AUTO_ZOOM_*`) lewat `Settings`
    3. `platform_settings["reframe"]` (override runtime dari admin panel)
    4. opsi per-task (`editing_options`) — mis. `zoom_level` lama

Kompatibilitas lama dipertahankan: `auto_zoom` (speaker/face/follow),
`zoom_level` (dipakai sebagai `maximum_zoom`), dan `auto_zoom_split`.
Tidak ada setting baru yang menduplikasi sistem settings yang sudah ada.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, Iterable, Mapping, Optional


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n", ""}:
        return False
    return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class ReframeConfig:
    """Parameter pipeline reframing. Semua satuan detik kecuali disebut lain."""

    # --- saklar fitur (bisa independen) ---
    enable_auto_zoom: bool = True
    enable_camera_follow: bool = True

    # --- deteksi & tracking ---
    # Pakai GPU untuk inferensi YOLO bila CUDAExecutionProvider tersedia.
    # False = paksa CPU (mis. image tanpa onnxruntime-gpu, atau hemat VRAM
    # saat GPU dipakai Whisper). Fallback CPU tetap otomatis bila CUDA gagal.
    prefer_cuda: bool = True
    detection_confidence: float = 0.35
    tracking_confidence: float = 0.25
    person_min_area_ratio: float = 0.010
    face_confidence: float = 0.62
    track_max_missed: int = 12
    track_min_hits: int = 3
    tracking_grace_period: float = 1.0
    primary_switch_hold: float = 1.5

    # --- analisis temporal ---
    analysis_fps: float = 8.0
    analysis_max_side: int = 960
    scene_cut_threshold: float = 0.55
    smoothing_window: float = 0.5

    # --- moment detection ---
    # Ambang skor: momen harus "layak" (subjek jelas + komposisi baik +
    # aktivitas), tetapi bukan hanya video dengan gerakan cepat.
    minimum_moment_score: float = 0.45
    minimum_moment_duration: float = 1.2
    minimum_subject_visibility: float = 0.60
    moment_merge_gap: float = 0.6
    speech_weight: float = 0.15

    # --- bobot skor momen (tidak ada satu indikator yang menentukan sendiri) ---
    weight_confidence: float = 0.18
    weight_face: float = 0.14
    weight_visibility: float = 0.16
    weight_motion: float = 0.16
    weight_activity: float = 0.12
    weight_face_size: float = 0.10
    weight_composition: float = 0.14

    # --- zoom ---
    minimum_zoom: float = 1.05
    # Batas atas zoom. Disamakan dengan pilihan terbesar di UI (2.0x) supaya
    # user tidak pernah mendapat zoom lebih besar dari yang ia lihat/pilih:
    # `zoom_level` hanya dikirim bila != 1.0, sehingga nilai default inilah yang
    # dipakai saat user memilih 1.0x atau saat `auto_zoom` tidak aktif.
    # Nilai ini tetap di-clamp ke [minimum_zoom, 3.0] oleh `sanitized()`.
    maximum_zoom: float = 2.00
    # Fraksi luas frame yang dianggap "pas" untuk satu subjek (bukan close-up).
    # 0.12 = subjek mengisi ~12% frame (kepala + badan terlihat).
    target_subject_fill: float = 0.12
    zoom_in_duration: float = 0.6
    hold_min_duration: float = 0.8
    zoom_out_duration: float = 0.8
    zoom_cooldown: float = 2.0

    # --- camera follow ---
    camera_smoothing: float = 0.35
    camera_dead_zone: float = 0.06
    camera_max_velocity: float = 0.055
    camera_motion_prediction: float = 0.35
    edge_margin: float = 0.10

    # --- debugging ---
    debug: bool = False

    # ------------------------------------------------------------------
    # Turunan / helper
    # ------------------------------------------------------------------
    def sanitized(self) -> "ReframeConfig":
        """Rapikan nilai agar aman dipakai (urutan zoom, durasi, bobot)."""
        cfg = ReframeConfig(**asdict(self))
        cfg.minimum_zoom = _clamp(cfg.minimum_zoom, 1.0, 3.0)
        cfg.maximum_zoom = _clamp(cfg.maximum_zoom, cfg.minimum_zoom, 3.0)
        cfg.detection_confidence = _clamp(cfg.detection_confidence, 0.05, 0.95)
        cfg.tracking_confidence = _clamp(cfg.tracking_confidence, 0.05, 0.95)
        cfg.minimum_moment_score = _clamp(cfg.minimum_moment_score, 0.0, 1.0)
        cfg.minimum_subject_visibility = _clamp(cfg.minimum_subject_visibility, 0.0, 1.0)
        cfg.minimum_moment_duration = max(0.2, cfg.minimum_moment_duration)
        cfg.zoom_in_duration = max(0.1, cfg.zoom_in_duration)
        cfg.zoom_out_duration = max(0.1, cfg.zoom_out_duration)
        cfg.hold_min_duration = max(0.0, cfg.hold_min_duration)
        cfg.zoom_cooldown = max(0.0, cfg.zoom_cooldown)
        cfg.camera_smoothing = _clamp(cfg.camera_smoothing, 0.0, 0.95)
        cfg.camera_dead_zone = _clamp(cfg.camera_dead_zone, 0.0, 0.4)
        cfg.camera_max_velocity = _clamp(cfg.camera_max_velocity, 0.005, 0.5)
        cfg.analysis_fps = _clamp(cfg.analysis_fps, 1.0, 30.0)
        cfg.speech_weight = _clamp(cfg.speech_weight, 0.0, 0.3)
        cfg.target_subject_fill = _clamp(cfg.target_subject_fill, 0.10, 0.80)
        cfg.edge_margin = _clamp(cfg.edge_margin, 0.0, 0.35)
        cfg.track_max_missed = max(1, int(cfg.track_max_missed))
        cfg.track_min_hits = max(1, int(cfg.track_min_hits))
        cfg.analysis_max_side = max(320, int(cfg.analysis_max_side))
        weights = {
            "weight_confidence": cfg.weight_confidence,
            "weight_face": cfg.weight_face,
            "weight_visibility": cfg.weight_visibility,
            "weight_motion": cfg.weight_motion,
            "weight_activity": cfg.weight_activity,
            "weight_face_size": cfg.weight_face_size,
            "weight_composition": cfg.weight_composition,
        }
        total = sum(max(0.0, value) for value in weights.values())
        if total <= 0:
            for name, value in (
                ("weight_confidence", 0.18),
                ("weight_face", 0.14),
                ("weight_visibility", 0.16),
                ("weight_motion", 0.16),
                ("weight_activity", 0.12),
                ("weight_face_size", 0.10),
                ("weight_composition", 0.14),
            ):
                setattr(cfg, name, value)
        else:
            # Normalisasi bobot ke total 1.0 supaya skor momen tetap 0..1.
            for name, value in weights.items():
                setattr(cfg, name, max(0.0, value) / total)
        return cfg

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def cache_key(self) -> str:
        """Bagian konfigurasi yang mempengaruhi hasil ANALISIS (bukan render)."""
        keys = (
            "detection_confidence",
            "tracking_confidence",
            "person_min_area_ratio",
            "face_confidence",
            "track_max_missed",
            "track_min_hits",
            "tracking_grace_period",
            "analysis_fps",
            "analysis_max_side",
            "scene_cut_threshold",
            "smoothing_window",
            "minimum_moment_score",
            "minimum_moment_duration",
            "minimum_subject_visibility",
            "moment_merge_gap",
            "speech_weight",
            "weight_confidence",
            "weight_face",
            "weight_visibility",
            "weight_motion",
            "weight_activity",
            "weight_face_size",
            "weight_composition",
            "enable_auto_zoom",
            "enable_camera_follow",
        )
        return "|".join(f"{name}={getattr(self, name)}" for name in keys)


FIELD_NAMES = {field.name for field in fields(ReframeConfig)}


def _coerce(name: str, value: Any, current: Any) -> Any:
    if isinstance(current, bool):
        return _bool(value, current)
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return current
    if isinstance(current, float):
        return _float(value, current)
    return value


def apply_overrides(
    config: ReframeConfig, values: Optional[Mapping[str, Any]]
) -> ReframeConfig:
    """Terapkan override dict (hanya key yang dikenal) ke config baru."""
    if not values:
        return config
    data = asdict(config)
    for key, value in values.items():
        name = str(key)
        if name not in FIELD_NAMES or value is None:
            continue
        data[name] = _coerce(name, value, data[name])
    return ReframeConfig(**data)


def _from_settings(settings: Any) -> Dict[str, Any]:
    """Ambil nilai REFRAME_* / AUTO_ZOOM_* dari objek Settings bila ada."""
    if settings is None:
        return {}
    values: Dict[str, Any] = {}
    for name in FIELD_NAMES:
        attr = f"REFRAME_{name.upper()}"
        if hasattr(settings, attr):
            values[name] = getattr(settings, attr)
    for legacy, target in (
        ("AUTO_ZOOM_MIN_ZOOM", "minimum_zoom"),
        ("AUTO_ZOOM_MAX_ZOOM", "maximum_zoom"),
        ("AUTO_ZOOM_ANALYSIS_FPS", "analysis_fps"),
        ("AUTO_ZOOM_DETECTION_CONFIDENCE", "detection_confidence"),
    ):
        if hasattr(settings, legacy):
            values.setdefault(target, getattr(settings, legacy))
    return values


def _from_platform_settings() -> Dict[str, Any]:
    """Override runtime dari tabel `platform_settings` (kalau ada key reframe)."""
    try:
        from app.services import platform_settings
    except Exception:  # pragma: no cover - modul opsional saat unit test
        return {}
    payload: Any = None
    for getter in ("get_reframe", "reframe_config", "get_auto_zoom"):
        func = getattr(platform_settings, getter, None)
        if callable(func):
            try:
                payload = func()
            except Exception:
                payload = None
            if payload:
                break
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def load_reframe_config(
    options: Optional[Mapping[str, Any]] = None,
    settings: Any = None,
    platform: Optional[Mapping[str, Any]] = None,
) -> ReframeConfig:
    """
    Bangun ReframeConfig dari semua sumber konfigurasi project.

    `options` adalah `editing_options` task (nama lama tetap dihormati).
    """
    if settings is None:
        try:
            from app.core.config import settings as global_settings

            settings = global_settings
        except Exception:  # pragma: no cover
            settings = None

    config = apply_overrides(ReframeConfig(), _from_settings(settings))
    config = apply_overrides(
        config, _from_platform_settings() if platform is None else platform
    )

    options = options or {}
    legacy: Dict[str, Any] = {}
    # `zoom_level` lama = seberapa besar zoom yang diminta user -> batas atas.
    if options.get("zoom_level") is not None:
        level = _float(options.get("zoom_level"), 0.0)
        if level > 1.0:
            legacy["maximum_zoom"] = level
    for key in (
        "enable_auto_zoom",
        "enable_camera_follow",
        "detection_confidence",
        "tracking_confidence",
        "minimum_moment_score",
        "minimum_moment_duration",
        "minimum_subject_visibility",
        "minimum_zoom",
        "maximum_zoom",
        "zoom_in_duration",
        "zoom_out_duration",
        "zoom_cooldown",
        "camera_smoothing",
        "camera_dead_zone",
        "tracking_grace_period",
        "analysis_fps",
        "debug",
    ):
        if options.get(key) is not None:
            legacy[key] = options.get(key)
    config = apply_overrides(config, legacy)
    # `REFRAME_DEVICE=cpu` memaksa deteksi ke CPU tanpa mengubah kode/opsi task.
    if os.environ.get("REFRAME_DEVICE", "").strip().lower() == "cpu":
        config.prefer_cuda = False
    return config.sanitized()


def merge_dicts(*items: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for item in items:
        if item:
            merged.update(dict(item))
    return merged


def iter_known(values: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
    for key, value in values.items():
        if key in FIELD_NAMES:
            yield key, value