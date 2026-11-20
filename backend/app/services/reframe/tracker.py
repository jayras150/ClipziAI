"""
Tracker person bergaya ByteTrack (tanpa dependency tambahan).

Bedanya dengan tracker IoU lama di processor:

    * asosiasi 2 tahap: high-score box dulu, lalu low-score box untuk track
      yang sudah mapan (ByteTrack) -> ID tidak mudah putus saat subjek
      berhenti/gerak cepat atau tertutup sebagian;
    * motion model (kecepatan + EMA) sehingga pencocokan memakai box prediksi,
      bukan box frame sebelumnya;
    * track buffer (`misses`) dan `state` (tentative/tracked/lost) sehingga
      deteksi palsu sesaat tidak pernah menjadi track `tracked`;
    * `min_hits` + `grace` supaya target tidak berpindah karena satu frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.reframe.detectors import Detection


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """IoU dua box xyxy."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    x: float
    y: float
    w: float
    h: float
    score: float
    frame: int = 0
    hits: int = 1
    misses: int = 0
    age: int = 1
    state: str = "tentative"  # tentative | tracked | lost
    vx: float = 0.0
    vy: float = 0.0
    history: List[Tuple[int, float, float, float, float]] = field(default_factory=list)
    face_ratio: float = 0.0
    face_visible: bool = False
    speech: bool = False

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    @property
    def xyxy(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def predicted_xyxy(self) -> Tuple[float, float, float, float]:
        return (self.x + self.vx, self.y + self.vy, self.x + self.vx + self.w, self.y + self.vy + self.h)

    def update(self, det: Detection, frame: int, alpha: float = 0.7) -> None:
        """Update box dengan EMA + estimasi kecepatan (motion model)."""
        prev_cx, prev_cy = self.cx, self.cy
        alpha = max(0.2, min(0.95, float(alpha)))
        self.x = alpha * det.x + (1.0 - alpha) * self.x
        self.y = alpha * det.y + (1.0 - alpha) * self.y
        self.w = alpha * det.w + (1.0 - alpha) * self.w
        self.h = alpha * det.h + (1.0 - alpha) * self.h
        self.score = alpha * det.score + (1.0 - alpha) * self.score
        self.vx = 0.6 * self.vx + 0.4 * (self.cx - prev_cx)
        self.vy = 0.6 * self.vy + 0.4 * (self.cy - prev_cy)
        self.frame = frame
        self.hits += 1
        self.misses = 0
        self.age += 1
        if self.hits >= 2 and self.state == "tentative":
            self.state = "tracked"
        self.history.append((frame, self.cx, self.cy, self.w, self.h))
        if len(self.history) > 240:
            del self.history[: len(self.history) - 240]

    def mark_missed(self, max_missed: int) -> None:
        self.misses += 1
        self.age += 1
        if self.misses > max_missed:
            self.state = "lost"
        elif self.state == "tracked":
            self.state = "lost"


class ByteTrackLite:
    """Tracker multi-person dengan asosiasi dua tahap."""

    def __init__(
        self,
        high_threshold: float = 0.35,
        low_threshold: float = 0.15,
        max_missed: int = 12,
        min_hits: int = 3,
        iou_threshold: float = 0.25,
        low_iou_threshold: float = 0.15,
    ) -> None:
        self.high_threshold = float(high_threshold)
        self.low_threshold = float(low_threshold)
        self.max_missed = int(max_missed)
        self.min_hits = int(min_hits)
        self.iou_threshold = float(iou_threshold)
        self.low_iou_threshold = float(low_iou_threshold)
        self.tracks: Dict[int, Track] = {}
        self._next_id = 1
        self.scene_id = 0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Scene cut: ID lama tidak boleh dipakai untuk subjek scene baru."""
        self.tracks.clear()
        self.scene_id += 1

    def update(self, detections: Sequence[Detection], frame: int) -> List[Track]:
        high = [det for det in detections if det.score >= self.high_threshold]
        low = [
            det
            for det in detections
            if self.low_threshold <= det.score < self.high_threshold
        ]

        active = [track for track in self.tracks.values() if track.state != "lost"]
        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()

        pairs = self._match(active, high, self.iou_threshold, use_prediction=True)
        for track_id, det_index in pairs:
            self.tracks[track_id].update(high[det_index], frame)
            matched_tracks.add(track_id)
            matched_dets.add(det_index)

        # Tahap 2 (ByteTrack): low-score box hanya untuk track yang sudah mapan.
        remaining = [
            track
            for track in active
            if track.track_id not in matched_tracks and track.hits >= self.min_hits
        ]
        pairs_low = self._match(remaining, low, self.low_iou_threshold, use_prediction=False)
        for track_id, det_index in pairs_low:
            self.tracks[track_id].update(low[det_index], frame, alpha=0.5)
            matched_tracks.add(track_id)
            matched_dets.add(det_index)

        for track in active:
            if track.track_id not in matched_tracks:
                track.mark_missed(self.max_missed)

        for det_index, det in enumerate(high):
            if det_index in matched_dets:
                continue
            self._spawn(det, frame)

        for track_id in [tid for tid, trk in self.tracks.items() if trk.state == "lost" and trk.misses > self.max_missed]:
            del self.tracks[track_id]

        return self.visible(frame)

    def _spawn(self, det: Detection, frame: int) -> Track:
        track = Track(
            track_id=self._next_id,
            x=det.x,
            y=det.y,
            w=det.w,
            h=det.h,
            score=det.score,
            frame=frame,
        )
        track.history.append((frame, track.cx, track.cy, track.w, track.h))
        self.tracks[track.track_id] = track
        self._next_id += 1
        return track

    def _match(
        self,
        tracks: Sequence[Track],
        detections: Sequence[Detection],
        threshold: float,
        use_prediction: bool,
    ) -> List[Tuple[int, int]]:
        if not tracks or not detections:
            return []
        candidates: List[Tuple[float, int, int]] = []
        for track in tracks:
            box = track.predicted_xyxy() if use_prediction else track.xyxy
            for index, det in enumerate(detections):
                score = iou(box, (det.x, det.y, det.x + det.w, det.y + det.h))
                if score >= threshold:
                    candidates.append((score, track.track_id, index))
        candidates.sort(reverse=True)
        used_tracks: set[int] = set()
        used_dets: set[int] = set()
        pairs: List[Tuple[int, int]] = []
        for _, track_id, det_index in candidates:
            if track_id in used_tracks or det_index in used_dets:
                continue
            used_tracks.add(track_id)
            used_dets.add(det_index)
            pairs.append((track_id, det_index))
        return pairs

    # ------------------------------------------------------------------
    def visible(self, frame: int) -> List[Track]:
        """Track yang benar-benar terlihat pada frame ini (bukan hasil prediksi)."""
        return [
            track
            for track in self.tracks.values()
            if track.frame == frame and track.state in {"tracked", "tentative"}
        ]

    def confirmed(self, frame: int, grace_frames: int = 0) -> List[Track]:
        """Track mapan yang masih dalam grace period (untuk camera hold)."""
        result: List[Track] = []
        for track in self.tracks.values():
            if track.hits < self.min_hits:
                continue
            if track.frame == frame or track.misses <= grace_frames:
                result.append(track)
        return result

    def get(self, track_id: Optional[int]) -> Optional[Track]:
        if track_id is None:
            return None
        return self.tracks.get(track_id)


def track_strength(
    track: Track,
    src_w: int,
    src_h: int,
    min_hits: int = 3,
) -> float:
    """
    Skor relevansi subjek: konsistensi (hits), ukuran, kedekatan tengah,
    keberadaan wajah, dan aktivitas bicara.

    Bobot ukuran sengaja kecil (0.10) supaya orang yang lewat dekat kamera
    sesaat tidak otomatis merebut posisi primary subject.
    """
    frame_area = max(1.0, float(src_w) * float(src_h))
    area_ratio = min(1.0, track.area / frame_area)
    center_dist = (
        ((track.cx - src_w / 2.0) ** 2 + (track.cy - src_h / 2.0) ** 2) ** 0.5
    )
    center_score = max(0.0, 1.0 - center_dist / max(1.0, 0.75 * src_w))
    consistency = min(1.0, track.hits / max(1.0, float(min_hits) * 4.0))
    face_bonus = 0.10 if track.face_visible else 0.0
    speech_bonus = 0.08 if track.speech else 0.0
    return (
        0.34 * consistency
        + 0.10 * min(1.0, area_ratio * 8.0)
        + 0.26 * center_score
        + 0.22 * min(1.0, track.score)
        + face_bonus
        + speech_bonus
    )