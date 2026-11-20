"""
Detektor person (YOLO11n ONNX) dan wajah (OpenCV YuNet).

Backend person, dipilih berurutan dan diverifikasi saat runtime:

    1. onnxruntime dengan CUDAExecutionProvider   (GPU Vast.ai)
    2. onnxruntime dengan CPUExecutionProvider    (fallback, selalu ada)
    3. cv2.dnn                                     (fallback bila ort hilang)
    4. None                                        (pipeline tetap jalan: crop tengah)

`session_providers()` melaporkan provider yang BENAR-BENAR aktif, bukan
sekadar "CUDA tersedia" — supaya klaim GPU bisa diverifikasi dari log/report.

Model dimuat sekali per proses (singleton + cache per path) sehingga worker
yang memproses banyak task tidak mengunduh/memuat ulang model.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0

DEFAULT_MODEL_DIRS = (
    os.environ.get("REFRAME_MODEL_DIR", ""),
    "/opt/reframe",
    "/opt/opencv-data",
)
YOLO_FILENAMES = ("yolo11n.onnx", "yolov8n.onnx")
YUNET_FILENAMES = ("face_detection_yunet_2023mar.onnx",)

YOLO_INPUT_SIZE = 640


@dataclass
class Detection:
    """Satu objek terdeteksi pada koordinat frame sumber."""

    x: float
    y: float
    w: float
    h: float
    score: float
    class_id: int = PERSON_CLASS_ID

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def clipped(self, width: float, height: float) -> "Detection":
        x1 = max(0.0, min(self.x, width - 1.0))
        y1 = max(0.0, min(self.y, height - 1.0))
        x2 = max(x1 + 1.0, min(self.x + self.w, width))
        y2 = max(y1 + 1.0, min(self.y + self.h, height))
        return Detection(x1, y1, x2 - x1, y2 - y1, self.score, self.class_id)


def _find_model(filenames: Sequence[str], explicit: Optional[str] = None) -> Optional[str]:
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    for directory in DEFAULT_MODEL_DIRS:
        if not directory:
            continue
        for name in filenames:
            candidates.append(str(Path(directory) / name))
    for path in candidates:
        try:
            if path and os.path.isfile(path) and os.path.getsize(path) > 100_000:
                return path
        except OSError:
            continue
    return None


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> List[int]:
    """NMS numpy sederhana (box xyxy)."""
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]
    keep: List[int] = []
    while order.size > 0:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[current], x1[rest])
        yy1 = np.maximum(y1[current], y1[rest])
        xx2 = np.minimum(x2[current], x2[rest])
        yy2 = np.minimum(y2[current], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[current] + areas[rest] - inter
        iou = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)
        order = rest[iou <= iou_threshold]
    return keep


def _letterbox(
    image: np.ndarray, size: int = YOLO_INPUT_SIZE
) -> Tuple[np.ndarray, float, int, int]:
    """Resize proporsional + padding abu-abu 114 (resep YOLO)."""
    height, width = image.shape[:2]
    scale = min(size / max(1, width), size / max(1, height))
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    import cv2

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, image.shape[2]), 114, dtype=image.dtype)
    pad_x = (size - new_w) // 2
    pad_y = (size - new_h) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized
    return canvas, scale, pad_x, pad_y


class PersonDetector:
    """
    Detektor person YOLO11n (COCO class 0).

    `detect_batch` menerima list frame BGR ukuran sama dan mengembalikan list
    deteksi per frame dalam koordinat frame asli.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence: float = 0.35,
        prefer_cuda: bool = True,
        input_size: int = YOLO_INPUT_SIZE,
    ) -> None:
        self.confidence = float(confidence)
        self.input_size = int(input_size)
        self.model_path = _find_model(YOLO_FILENAMES, model_path)
        self.backend = "none"
        self.providers: List[str] = []
        self._session: Any = None
        self._net: Any = None
        self._input_name = ""
        if not self.model_path:
            logger.warning(
                "Model YOLO11n ONNX tidak ditemukan; deteksi person nonaktif "
                "(fallback crop tengah). Cari di: %s",
                ", ".join(path for path in DEFAULT_MODEL_DIRS if path),
            )
            return
        self._init_onnxruntime(prefer_cuda)
        if self._session is None:
            self._init_cv2_dnn()

    # ------------------------------------------------------------------
    def _init_onnxruntime(self, prefer_cuda: bool) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:  # pragma: no cover - tergantung image
            logger.info("onnxruntime tidak tersedia (%s); memakai cv2.dnn", exc)
            return

        available = list(ort.get_available_providers())
        wanted: List[str] = []
        if prefer_cuda and "CUDAExecutionProvider" in available:
            wanted.append("CUDAExecutionProvider")
        if "CPUExecutionProvider" in available:
            wanted.append("CPUExecutionProvider")
        if not wanted:
            logger.warning(
                "onnxruntime tidak punya provider yang bisa dipakai (available=%s)",
                ",".join(available) or "-",
            )
            return

        # Log eksplisit ALASAN CUDA tidak dipakai: tanpa ini, worker GPU yang
        # ternyata jatuh ke CPU hanya terlihat dari "backend=cpu" tanpa sebab.
        if prefer_cuda and "CUDAExecutionProvider" not in available:
            logger.warning(
                "CUDAExecutionProvider tidak tersedia (available=%s). "
                "Pasang onnxruntime-gpu di image GPU, atau set "
                "REFRAME_DEVICE=cpu untuk menonaktifkan peringatan ini.",
                ",".join(available) or "-",
            )
        elif not prefer_cuda:
            logger.info("CUDA dimatikan lewat konfigurasi (REFRAME_DEVICE=cpu)")

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2)))
        try:
            self._session = ort.InferenceSession(
                self.model_path, sess_options=options, providers=wanted
            )
        except Exception as exc:
            logger.warning("Inisialisasi onnxruntime gagal (%s); coba CPU", exc)
            try:
                self._session = ort.InferenceSession(
                    self.model_path, sess_options=options, providers=["CPUExecutionProvider"]
                )
            except Exception as exc2:
                logger.warning("onnxruntime CPU juga gagal: %s", exc2)
                self._session = None
                return

        self.providers = list(self._session.get_providers())
        self._input_name = self._session.get_inputs()[0].name
        self.backend = "cuda" if "CUDAExecutionProvider" in self.providers else "cpu"
        # ORT bisa "menerima" CUDA di daftar provider lalu tetap jatuh ke CPU
        # saat runtime (lib CUDA/cuDNN tidak lengkap). Bandingkan permintaan vs
        # hasil supaya klaim GPU di log selalu sesuai kenyataan.
        if "CUDAExecutionProvider" in wanted and self.backend != "cuda":
            logger.error(
                "CUDA diminta tetapi sesi aktif memakai %s; periksa lib CUDA/cuDNN "
                "worker (onnxruntime-gpu butuh cuDNN 9 + CUDA 12).",
                ",".join(self.providers) or "-",
            )
        logger.info(
            "YOLO11n aktif: backend=%s providers=%s model=%s ort=%s",
            self.backend,
            ", ".join(self.providers),
            self.model_path,
            getattr(ort, "__version__", "?"),
        )

    def _init_cv2_dnn(self) -> None:
        try:
            import cv2
        except Exception:  # pragma: no cover
            return
        try:
            self._net = cv2.dnn.readNetFromONNX(self.model_path)
            # Coba DNN CUDA bila opencv dibangun dengan CUDA; abaikan bila gagal.
            # Catatan: OpenCV 5.x memakai graph engine baru yang belum mendukung
            # target CUDA, jadi backend CPU adalah default yang aman.
            try:
                import cv2 as _cv2

                if not (hasattr(_cv2, "cuda") and _cv2.cuda.getCudaEnabledDeviceCount() > 0):
                    raise AttributeError("no CUDA backend")
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
                self.backend = "cuda-dnn"
            except Exception:
                self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_DEFAULT)
                self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                self.backend = "cpu-dnn"
            self.providers = [self.backend]
            logger.info("YOLO11n aktif via cv2.dnn (%s)", self.backend)
        except Exception as exc:
            logger.warning("cv2.dnn gagal memuat model YOLO: %s", exc)
            self._net = None
            self.backend = "none"
            self.providers = []

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._session is not None or self._net is not None

    def detect_batch(self, frames: Sequence[np.ndarray]) -> List[List[Detection]]:
        if not frames:
            return []
        if self._session is not None:
            try:
                return self._detect_ort(frames)
            except Exception as exc:
                logger.warning("Inferensi YOLO ORT gagal (%s); pindah ke cv2.dnn", exc)
                self._session = None
                self._init_cv2_dnn()
        if self._net is not None:
            return [self._detect_dnn(frame) for frame in frames]
        return [[] for _ in frames]

    def detect(self, frame: np.ndarray) -> List[Detection]:
        result = self.detect_batch([frame])
        return result[0] if result else []

    # ------------------------------------------------------------------
    def _preprocess(self, frames: Sequence[np.ndarray]) -> Tuple[np.ndarray, List[Tuple[float, int, int]]]:
        import cv2

        tensors: List[np.ndarray] = []
        metas: List[Tuple[float, int, int]] = []
        for frame in frames:
            canvas, scale, pad_x, pad_y = _letterbox(frame, self.input_size)
            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            tensor = rgb.astype(np.float32) / 255.0
            tensors.append(np.transpose(tensor, (2, 0, 1)))
            metas.append((scale, pad_x, pad_y))
        return np.stack(tensors, axis=0), metas

    def _detect_ort(self, frames: Sequence[np.ndarray]) -> List[List[Detection]]:
        batch, metas = self._preprocess(frames)
        outputs = self._session.run(None, {self._input_name: batch})
        raw = np.asarray(outputs[0])
        results: List[List[Detection]] = []
        for index, frame in enumerate(frames):
            pred = raw[index] if raw.ndim == 3 else raw
            results.append(self._decode(pred, metas[index], frame.shape[1], frame.shape[0]))
        return results

    def _decode(
        self,
        pred: np.ndarray,
        meta: Tuple[float, int, int],
        src_w: int,
        src_h: int,
    ) -> List[Detection]:
        """Decode output [84, anchors] (YOLOv8/11) -> deteksi person."""
        if pred.ndim != 2:
            return []
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T  # -> [anchors, 84]
        if pred.shape[1] < 5:
            return []
        class_scores = pred[:, 4:]
        if class_scores.shape[1] <= PERSON_CLASS_ID:
            return []
        person_scores = class_scores[:, PERSON_CLASS_ID]
        keep_mask = person_scores >= self.confidence
        if not np.any(keep_mask):
            return []
        boxes = pred[keep_mask, :4]
        scores = person_scores[keep_mask]
        xyxy = np.empty_like(boxes)
        xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2.0
        xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2.0
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2.0
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2.0
        keep = _nms(xyxy, scores)
        scale, pad_x, pad_y = meta
        scale = scale or 1.0
        detections: List[Detection] = []
        for idx in keep:
            x1 = (float(xyxy[idx, 0]) - pad_x) / scale
            y1 = (float(xyxy[idx, 1]) - pad_y) / scale
            x2 = (float(xyxy[idx, 2]) - pad_x) / scale
            y2 = (float(xyxy[idx, 3]) - pad_y) / scale
            det = Detection(x1, y1, x2 - x1, y2 - y1, float(scores[idx]))
            detections.append(det.clipped(float(src_w), float(src_h)))
        return detections

    def _detect_dnn(self, frame: np.ndarray) -> List[Detection]:
        import cv2

        canvas, scale, pad_x, pad_y = _letterbox(frame, self.input_size)
        blob = cv2.dnn.blobFromImage(
            canvas, 1.0 / 255.0, (self.input_size, self.input_size),
            swapRB=True, crop=False,
        )
        self._net.setInput(blob)
        raw = self._net.forward()
        pred = np.asarray(raw)
        if pred.ndim == 3:
            pred = pred[0]
        return self._decode(pred, (scale, pad_x, pad_y), frame.shape[1], frame.shape[0])


class FaceDetector:
    """Wrapper YuNet (cv2.FaceDetectorYN) — sinyal tambahan, bukan syarat."""

    def __init__(
        self,
        width: int,
        height: int,
        confidence: float = 0.62,
        model_path: Optional[str] = None,
    ) -> None:
        self.width = max(2, int(width))
        self.height = max(2, int(height))
        self.confidence = float(confidence)
        self.model_path = _find_model(YUNET_FILENAMES, model_path)
        self._detector: Any = None
        self.backend = "none"
        if not self.model_path:
            return
        try:
            import cv2
        except Exception:  # pragma: no cover
            return
        if not hasattr(cv2, "FaceDetectorYN"):
            return
        try:
            self._detector = cv2.FaceDetectorYN.create(
                self.model_path,
                "",
                (self.width, self.height),
                score_threshold=self.confidence,
                nms_threshold=0.3,
                top_k=5000,
            )
            self._detector.setInputSize((self.width, self.height))
            self.backend = "yunet"
        except Exception as exc:
            logger.warning("YuNet gagal dimuat: %s", exc)
            self._detector = None

    @property
    def available(self) -> bool:
        return self._detector is not None

    def detect(self, frame_small: np.ndarray) -> List[Detection]:
        """Deteksi pada frame yang sudah diperkecil; koordinat = frame tersebut."""
        if self._detector is None:
            return []
        try:
            _, faces = self._detector.detect(frame_small)
        except Exception:
            return []
        if faces is None:
            return []
        detections: List[Detection] = []
        for box in faces:
            score = float(box[-1])
            if score < self.confidence:
                continue
            w = float(box[2])
            h = float(box[3])
            if w < 2.0 or h < 2.0:
                continue
            detections.append(
                Detection(float(box[0]), float(box[1]), w, h, score, class_id=-1)
            )
        return detections


_PERSON_CACHE: Dict[str, PersonDetector] = {}
_FACE_CACHE: Dict[str, FaceDetector] = {}
_CACHE_LOCK = threading.Lock()


def get_person_detector(
    confidence: float = 0.35, prefer_cuda: bool = True, model_path: Optional[str] = None
) -> PersonDetector:
    """Detektor person tunggal per (model, confidence, preferensi GPU)."""
    key = f"{model_path or 'auto'}|{round(float(confidence), 3)}|{bool(prefer_cuda)}"
    with _CACHE_LOCK:
        detector = _PERSON_CACHE.get(key)
        if detector is None:
            detector = PersonDetector(model_path, confidence, prefer_cuda)
            _PERSON_CACHE[key] = detector
        return detector


def get_face_detector(
    width: int, height: int, confidence: float = 0.62, model_path: Optional[str] = None
) -> FaceDetector:
    key = f"{model_path or 'auto'}|{int(width)}x{int(height)}|{round(float(confidence), 3)}"
    with _CACHE_LOCK:
        detector = _FACE_CACHE.get(key)
        if detector is None:
            detector = FaceDetector(width, height, confidence, model_path)
            _FACE_CACHE[key] = detector
        return detector


def reset_detector_cache() -> None:
    """Dipakai test untuk memastikan model dimuat ulang saat perlu."""
    with _CACHE_LOCK:
        _PERSON_CACHE.clear()
        _FACE_CACHE.clear()


def model_fingerprint(path: Optional[str]) -> str:
    if not path or not os.path.isfile(path):
        return "none"
    stat = os.stat(path)
    return hashlib.sha1(f"{path}:{stat.st_size}".encode()).hexdigest()[:12]