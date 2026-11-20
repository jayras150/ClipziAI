"""
Ekstraksi fitur per sample frame untuk Moment Detection Engine.

Semua fitur berada di rentang 0..1 supaya bobot momen mudah dituning dan
skor akhir tetap bermakna. Fitur dihitung dari data analisis (deteksi +
track + wajah + statistik frame), bukan dari tebakan.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.reframe.detectors import Detection
from app.services.reframe.tracker import Track


@dataclass
class FrameFeatures:
    time: float
    person_count: int = 0
    primary_id: Optional[int] = None
    person_score: float = 0.0
    face_score: float = 0.0
    face_ratio: float = 0.0
    visibility: float = 0.0
    bbox_area_ratio: float = 0.0
    motion: float = 0.0
    activity: float = 0.0
    composition: float = 0.0
    headroom: float = 0.0
    edge_clip: float = 0.0
    stability: float = 0.0
    scene_cut: bool = False
    speech: float = 0.0
    # bbox subjek dalam koordinat sumber (untuk trajectory & report)
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    face_box: Optional[Tuple[float, float, float, float]] = None
    extras: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["bbox"] = list(self.bbox)
        data["face_box"] = list(self.face_box) if self.face_box else None
        return data


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else float(value))


def visibility_ratio(box: Sequence[float], src_w: float, src_h: float) -> float:
    """Bagian bbox yang masih berada di dalam frame (0..1)."""
    x, y, w, h = box
    area = max(1e-6, w * h)
    x1, y1 = max(0.0, x), max(0.0, y)
    x2, y2 = min(src_w, x + w), min(src_h, y + h)
    inside = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return _clamp01(inside / area)


def headroom_ratio(box: Sequence[float], src_h: float) -> float:
    """Ruang kosong di atas kepala relatif tinggi frame (0 = mentok atas)."""
    y = float(box[1])
    return _clamp01(y / max(1.0, src_h))


def edge_clip_ratio(box: Sequence[float], src_w: float, src_h: float) -> float:
    """Seberapa banyak subjek terpotong tepi frame (0 = utuh, 1 = terpotong total)."""
    x, y, w, h = box
    clipped = 0.0
    if x < 0:
        clipped += min(1.0, -x / max(1.0, w))
    if y < 0:
        clipped += min(1.0, -y / max(1.0, h))
    if x + w > src_w:
        clipped += min(1.0, (x + w - src_w) / max(1.0, w))
    if y + h > src_h:
        clipped += min(1.0, (y + h - src_h) / max(1.0, h))
    return _clamp01(clipped / 2.0)


def composition_score(
    box: Sequence[float],
    src_w: float,
    src_h: float,
    edge_margin: float = 0.10,
) -> float:
    """
    Kualitas komposisi: subjek dekat sepertiga/tengah frame, tidak menempel
    tepi, dan masih punya ruang di atas kepala.
    """
    x, y, w, h = box
    cx_ratio = (x + w / 2.0) / max(1.0, src_w)
    cy_ratio = (y + h / 2.0) / max(1.0, src_h)
    center_score = 1.0 - min(1.0, abs(cx_ratio - 0.5) * 2.0)
    vertical = 1.0 - min(1.0, abs(cy_ratio - 0.52) * 2.0)
    margin = max(0.0, float(edge_margin))
    inside = 1.0
    if x < src_w * margin:
        inside -= 0.3
    if x + w > src_w * (1.0 - margin):
        inside -= 0.3
    if y < src_h * margin * 0.4:
        inside -= 0.2
    headroom = headroom_ratio(box, src_h)
    headroom_score = 1.0 if 0.06 <= headroom <= 0.45 else max(0.0, 1.0 - abs(headroom - 0.18) * 3.0)
    return _clamp01(0.35 * center_score + 0.15 * vertical + max(0.0, inside) * 0.30 + 0.20 * headroom_score)


def motion_score(
    history: Sequence[Tuple[int, float, float, float, float]],
    src_w: int,
    src_h: int,
    window: int = 8,
) -> float:
    """Kecepatan subjek ternormalisasi (piksel/detik relatif dimensi frame)."""
    if len(history) < 2:
        return 0.0
    recent = list(history)[-window:]
    first = recent[0]
    last = recent[-1]
    frames = max(1, int(last[0] - first[0]))
    dx = (last[1] - first[1]) / max(1.0, float(src_w))
    dy = (last[2] - first[2]) / max(1.0, float(src_h))
    speed = (dx * dx + dy * dy) ** 0.5 / frames
    # 0.02 lebar-frame per sample = gerakan jelas -> skor 1.0
    return _clamp01(speed / 0.02)


def activity_score(histories: Sequence[Sequence[Tuple[int, float, float, float, float]]], src_w: int, src_h: int) -> float:
    """
    Aktivitas visual: gabungan perpindahan subjek dan perubahan ukuran bbox
    (mendekat/menjauh). Dipakai bersama `motion_score`, bukan pengganti.
    """
    if not histories:
        return 0.0
    total = 0.0
    counted = 0
    for history in histories:
        if len(history) < 3:
            continue
        recent = list(history)[-8:]
        first, last = recent[0], recent[-1]
        frames = max(1, int(last[0] - first[0]))
        move = (
            ((last[1] - first[1]) / max(1.0, src_w)) ** 2
            + ((last[2] - first[2]) / max(1.0, src_h)) ** 2
        ) ** 0.5 / frames
        size_change = abs(last[3] - first[3]) / max(1.0, first[3])
        total += _clamp01(move / 0.02) * 0.7 + _clamp01(size_change * 2.0) * 0.3
        counted += 1
    return _clamp01(total / counted) if counted else 0.0


def stability_score(history: Sequence[Tuple[int, float, float, float, float]]) -> float:
    """
    Temporal consistency: track yang stabil (banyak observasi, gerak wajar)
    lebih dipercaya daripada track yang muncul-hilang.
    """
    if not history:
        return 0.0
    return _clamp01(len(history) / 24.0)


def face_size_ratio(face_box: Optional[Sequence[float]], src_w: float, src_h: float) -> float:
    """Luas wajah relatif frame (dipakai untuk menahan zoom berlebihan)."""
    if not face_box:
        return 0.0
    _, _, w, h = face_box
    return _clamp01((w * h) / max(1.0, src_w * src_h))


def match_face_to_person(
    person: Sequence[float],
    faces: Sequence[Detection],
) -> Optional[Detection]:
    """
    Pasangkan wajah ke person: wajah harus berada dalam area kepala person
    (atas 45% bbox dan horizontal di dalam bbox).
    """
    x, y, w, h = person
    head_bottom = y + h * 0.45
    best: Optional[Detection] = None
    best_score = 0.0
    for face in faces:
        fcx, fcy = face.cx, face.cy
        if not (x - w * 0.10 <= fcx <= x + w * 1.10):
            continue
        if not (y - h * 0.10 <= fcy <= head_bottom):
            continue
        score = face.score * (1.0 - abs(fcx - (x + w / 2.0)) / max(1.0, w))
        if score > best_score:
            best = face
            best_score = score
    return best


def extract_features(
    time: float,
    frame_index: int,
    tracks: Sequence[Track],
    faces: Sequence[Detection],
    src_w: int,
    src_h: int,
    primary: Optional[Track],
    scene_cut: bool = False,
    frame_diff: float = 0.0,
    speech: float = 0.0,
    edge_margin: float = 0.10,
) -> FrameFeatures:
    """Bangun satu FrameFeatures dari hasil deteksi/tracking satu sample."""
    features = FrameFeatures(time=time, scene_cut=scene_cut, speech=_clamp01(speech))
    features.person_count = len(tracks)
    if primary is None:
        return features

    box = (primary.x, primary.y, primary.w, primary.h)
    face = match_face_to_person(box, faces)
    features.primary_id = primary.track_id
    features.bbox = box
    features.person_score = _clamp01(primary.score)
    features.visibility = visibility_ratio(box, float(src_w), float(src_h))
    features.bbox_area_ratio = _clamp01(primary.area / max(1.0, float(src_w) * float(src_h)))
    features.headroom = headroom_ratio(box, float(src_h))
    features.edge_clip = edge_clip_ratio(box, float(src_w), float(src_h))
    features.composition = composition_score(box, float(src_w), float(src_h), edge_margin)
    features.motion = motion_score(primary.history, src_w, src_h)
    features.activity = activity_score([track.history for track in tracks], src_w, src_h)
    features.stability = stability_score(primary.history)
    if face is not None:
        features.face_score = _clamp01(face.score)
        features.face_box = (face.x, face.y, face.w, face.h)
        features.face_ratio = face_size_ratio(features.face_box, float(src_w), float(src_h))
    # Gerak global frame (kamera goyang / cut) menambah "activity" sedikit.
    features.extras["frame_diff"] = _clamp01(frame_diff * 4.0)
    return features


def smooth_series(values: Sequence[float], window: int) -> List[float]:
    """Moving average simetris (edge padding) untuk fitur temporal."""
    count = len(values)
    if count == 0 or window <= 1:
        return list(values)
    window = window if window % 2 == 1 else window + 1
    pad = window // 2
    padded = [values[0]] * pad + list(values) + [values[-1]] * pad
    out: List[float] = []
    total = 0.0
    for index in range(len(padded)):
        total += padded[index]
        if index >= window:
            total -= padded[index - window]
        if index >= window - 1:
            out.append(total / window)
    return out[:count]