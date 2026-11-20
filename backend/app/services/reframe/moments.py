"""
Moment Detection Engine.

Ini yang membedakan sistem ini dari "person detected -> zoom". Alurnya:

    1. fitur per sample di-smooth secara temporal;
    2. skor momen dihitung dari BOBOT BANYAK INDIKATOR (tidak ada satu pun
       indikator yang bisa memicu zoom sendiri);
    3. gate keras: tidak ada subjek -> tidak ada momen; subjek tidak terlihat;
       wajah sudah memenuhi frame (close-up) -> zoom ditolak;
    4. kandidat momen harus melewati `minimum_moment_score` dan
       `minimum_moment_duration`; kandidat pendek (false detection) dibuang;
    5. jeda antar momen dijaga dengan `zoom_cooldown`.

Setiap momen menyimpan `reason` supaya keputusan bisa diaudit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence

from app.services.reframe.config import ReframeConfig
from app.services.reframe.features import FrameFeatures, smooth_series


def _clamp(value: float, low: float, high: float) -> float:
    return high if value > high else (low if value < low else value)


def _clamp01(value: float) -> float:
    return _clamp(float(value), 0.0, 1.0)


@dataclass
class Moment:
    start_time: float
    end_time: float
    confidence: float
    moment_score: float
    target_id: Optional[int]
    target_bbox: List[float] = field(default_factory=list)
    recommended_zoom: float = 1.0
    recommended_camera_position: List[float] = field(default_factory=list)
    reason: str = ""
    reasons: List[str] = field(default_factory=list)
    face_ratio: float = 0.0
    visibility: float = 0.0
    activity: float = 0.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["duration"] = round(self.duration, 3)
        data["start_time"] = round(self.start_time, 3)
        data["end_time"] = round(self.end_time, 3)
        data["confidence"] = round(self.confidence, 4)
        data["moment_score"] = round(self.moment_score, 4)
        data["recommended_zoom"] = round(self.recommended_zoom, 4)
        return data


@dataclass
class MomentDecision:
    """Rincian keputusan per sample (untuk debug/report)."""

    time: float
    score: float
    accepted: bool
    reason: str
    target_id: Optional[int] = None


@dataclass
class MomentResult:
    moments: List[Moment] = field(default_factory=list)
    decisions: List[MomentDecision] = field(default_factory=list)
    skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)

    def _bump(self, reason: str) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1


class MomentDetectionEngine:
    """Skoring + seleksi momen berbasis fitur temporal."""

    def __init__(self, config: ReframeConfig) -> None:
        self.config = config.sanitized()

    # ------------------------------------------------------------------
    def score(self, features: FrameFeatures) -> float:
        """
        Skor momen 0..1 dari fitur yang sudah dipercaya.

        Bobot dinormalisasi di ReframeConfig.sanitized(); speech hanya
        menambah sebagian kecil (maks `speech_weight`) dan TIDAK PERNAH
        menjadi penentu tunggal.
        """
        cfg = self.config
        face_component = 0.6 * features.face_score + 0.4 * min(1.0, features.face_ratio * 40.0)
        motion_component = 0.7 * features.motion + 0.3 * features.activity
        # "Subject validity": subjek ini benar-benar sah dan layak difokuskan?
        # Gabungan track yang sudah mapan (stability), deteksi yang konsisten,
        # wajah yang jelas, dan subjek yang utuh di frame. Tanpa komponen ini,
        # subjek yang sah tetapi diam akan mendapat skor rendah secara tidak
        # wajar (bug desain: 'kualitas momen' dianggap sama dengan 'aktivitas').
        validity = (
            0.40 * features.stability
            + 0.30 * features.person_score
            + 0.20 * features.visibility
            + 0.10 * face_component
        )
        quality = (
            cfg.weight_confidence * features.person_score
            + cfg.weight_face * face_component
            + cfg.weight_visibility * features.visibility
            + cfg.weight_motion * motion_component
            + cfg.weight_activity * features.activity
            + cfg.weight_face_size * min(1.0, features.face_ratio * 30.0)
            + cfg.weight_composition * features.composition
        )
        base = 0.55 * validity + 0.45 * quality
        # Speech hanya penguat kecil dan tidak bisa membuat skor > 1.
        speech_boost = cfg.speech_weight * _clamp01(features.speech)
        return _clamp01(base * (1.0 - cfg.speech_weight) + speech_boost)

    # ------------------------------------------------------------------
    def _gate(self, features: FrameFeatures) -> Optional[str]:
        """Alasan penolakan keras (bukan sekadar skor rendah)."""
        cfg = self.config
        if features.person_count <= 0 or features.primary_id is None:
            return "no_person"
        if features.visibility < cfg.minimum_subject_visibility:
            return "subject_not_visible"
        # Wajah sudah memenuhi frame: zoom tambahan hanya memotong kepala.
        # Ambang 10% luas frame (setara wajah ~1/3 lebar frame); di bawah itu
        # subjek masih jauh dan zoom justru membantu.
        if features.face_ratio >= 0.10 and features.face_score >= 0.7:
            return "face_fills_frame"
        # Subjek menempel tepi frame: crop akan memotong badan.
        if features.edge_clip >= 0.35:
            return "subject_edge_clipped"
        if features.bbox_area_ratio <= 0.0:
            return "no_person"
        return None

    def _recommended_zoom(self, features: FrameFeatures) -> float:
        """
        Zoom dari rasio isi subjek terhadap target fill, dibatasi min/max dan
        ditahan bila wajah sudah besar (close-up).

        Untuk subjek yang sangat kecil (mis. orang di kejauhan) zoom dinaikkan
        bertahap: cukup untuk memperjelas subjek tanpa memaksa zoom maksimum
        pada satu orang yang berjalan jauh.
        """
        cfg = self.config
        area_ratio = max(1e-5, features.bbox_area_ratio)
        raw = (cfg.target_subject_fill / area_ratio) ** 0.5
        # Subjek < 2% luas frame: butuh zoom lebih agresif, tetapi tetap
        # dibatasi `maximum_zoom` (bukan tak terhingga).
        if area_ratio < 0.02:
            raw = max(raw, 1.0 + 0.6 * (cfg.maximum_zoom - 1.0))
        if features.face_ratio > 0.0:
            # Wajah besar -> jangan menambah zoom karena subjek sudah dekat.
            face_pressure = _clamp01((features.face_ratio - 0.04) / 0.06)
            raw *= 1.0 - 0.55 * face_pressure
        return _clamp(raw, cfg.minimum_zoom, cfg.maximum_zoom)

    # ------------------------------------------------------------------
    def detect(self, features: Sequence[FrameFeatures]) -> MomentResult:
        """Seleksi momen dari deret fitur (satu fitur per sample analisis)."""
        cfg = self.config
        result = MomentResult()
        if not features:
            return result

        times = [item.time for item in features]
        window = max(1, int(round(cfg.smoothing_window * cfg.analysis_fps)))
        smoothed = {
            name: smooth_series([float(getattr(item, name)) for item in features], window)
            for name in (
                "person_score",
                "face_score",
                "visibility",
                "motion",
                "activity",
                "composition",
                "stability",
                "face_ratio",
                "edge_clip",
                "speech",
            )
        }

        scores: List[float] = []
        gated: List[Optional[str]] = []
        for index, item in enumerate(features):
            view = FrameFeatures(
                time=item.time,
                person_count=item.person_count,
                primary_id=item.primary_id,
                person_score=smoothed["person_score"][index],
                face_score=smoothed["face_score"][index],
                face_ratio=smoothed["face_ratio"][index],
                visibility=smoothed["visibility"][index],
                bbox_area_ratio=item.bbox_area_ratio,
                motion=smoothed["motion"][index],
                activity=smoothed["activity"][index],
                composition=smoothed["composition"][index],
                headroom=item.headroom,
                edge_clip=smoothed["edge_clip"][index],
                stability=smoothed["stability"][index],
                scene_cut=item.scene_cut,
                speech=smoothed["speech"][index],
                bbox=item.bbox,
                face_box=item.face_box,
            )
            gate = self._gate(view)
            gated.append(gate)
            score = 0.0 if gate else self.score(view)
            scores.append(score)
            if gate:
                result.decisions.append(MomentDecision(item.time, 0.0, False, gate, item.primary_id))
            elif score < cfg.minimum_moment_score:
                result.decisions.append(
                    MomentDecision(item.time, score, False, "score_below_threshold", item.primary_id)
                )
            else:
                result.decisions.append(MomentDecision(item.time, score, True, "candidate", item.primary_id))

        # --- kandidat: himpunan sample berurutan yang lolos ambang ---
        runs: List[tuple[int, int]] = []
        start: Optional[int] = None
        for index, decision in enumerate(result.decisions):
            if decision.accepted:
                if start is None:
                    start = index
            elif start is not None:
                runs.append((start, index - 1))
                start = None
        if start is not None:
            runs.append((start, len(result.decisions) - 1))

        sample_dt = 1.0 / max(1e-3, cfg.analysis_fps)
        max_gap = max(1, int(round(cfg.moment_merge_gap * cfg.analysis_fps)))
        merged: List[tuple[int, int]] = []
        for run in runs:
            if merged and run[0] - merged[-1][1] <= max_gap:
                merged[-1] = (merged[-1][0], run[1])
            else:
                merged.append(run)

        last_end = -1e9
        for first, last in merged:
            start_time = max(0.0, times[first] - sample_dt / 2.0)
            end_time = times[last] + sample_dt / 2.0
            duration = end_time - start_time
            if duration < cfg.minimum_moment_duration:
                result._bump("too_short")
                continue
            if start_time - last_end < cfg.zoom_cooldown:
                result._bump("cooldown")
                continue

            segment = features[first : last + 1]
            primary_ids = [item.primary_id for item in segment if item.primary_id is not None]
            if not primary_ids:
                result._bump("no_person")
                continue
            target_id = max(set(primary_ids), key=primary_ids.count)
            target_frames = [item for item in segment if item.primary_id == target_id]
            if len(target_frames) < max(2, int(0.5 * len(segment))):
                result._bump("target_inconsistent")
                continue

            avg_score = sum(scores[i] for i in range(first, last + 1)) / (last - first + 1)
            confidence = sum(item.person_score for item in target_frames) / len(target_frames)
            zoom_values = [self._recommended_zoom(item) for item in target_frames]
            recommended_zoom = sum(zoom_values) / len(zoom_values)
            last_box = target_frames[len(target_frames) // 2].bbox
            reasons = self._reason_text(target_frames, avg_score)

            result.moments.append(
                Moment(
                    start_time=start_time,
                    end_time=end_time,
                    confidence=_clamp01(confidence),
                    moment_score=_clamp01(avg_score),
                    target_id=target_id,
                    target_bbox=[round(value, 2) for value in last_box],
                    recommended_zoom=round(recommended_zoom, 4),
                    recommended_camera_position=[
                        round(last_box[0] + last_box[2] / 2.0, 2),
                        round(last_box[1] + last_box[3] / 2.0, 2),
                    ],
                    reason="; ".join(reasons) if reasons else "valid visual moment",
                    reasons=reasons,
                    face_ratio=round(
                        sum(item.face_ratio for item in target_frames) / len(target_frames), 4
                    ),
                    visibility=round(
                        sum(item.visibility for item in target_frames) / len(target_frames), 4
                    ),
                    activity=round(
                        sum(item.activity for item in target_frames) / len(target_frames), 4
                    ),
                )
            )
            last_end = end_time

        return result

    # ------------------------------------------------------------------
    def _reason_text(self, frames: Sequence[FrameFeatures], score: float) -> List[str]:
        reasons: List[str] = []
        if not frames:
            return reasons
        count = float(len(frames))
        face_avg = sum(item.face_score for item in frames) / count
        motion_avg = sum(item.motion for item in frames) / count
        activity_avg = sum(item.activity for item in frames) / count
        comp_avg = sum(item.composition for item in frames) / count
        vis_avg = sum(item.visibility for item in frames) / count
        if face_avg >= 0.7:
            reasons.append("clear face visibility")
        if motion_avg >= 0.35 or activity_avg >= 0.35:
            reasons.append("strong subject activity")
        if comp_avg >= 0.7:
            reasons.append("good composition")
        if vis_avg >= 0.9:
            reasons.append("subject fully in frame")
        if not reasons:
            reasons.append(f"sustained valid subject (score {score:.2f})")
        return reasons


def moments_summary(moments: Sequence[Moment]) -> List[Dict[str, object]]:
    return [moment.to_dict() for moment in moments]