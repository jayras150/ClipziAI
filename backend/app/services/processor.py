"""
Video Processor Service - FFmpeg, PySceneDetect, smart crop, burn subtitle
"""
import os
import asyncio
import functools
import logging
import re
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class VideoProcessor:
    """Process videos: scene detection, smart crop 9:16, burn subtitle, compress."""
    
    def __init__(self, work_dir: str = "./work"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    async def detect_scenes(self, video_path: str) -> List[Dict[str, Any]]:
        """Detect scene changes using PySceneDetect (API 0.6+/0.7+)."""
        try:
            from scenedetect import ContentDetector, detect  # noqa: F401
        except ImportError:
            return [{"start": 0, "end": 60, "confidence": 1.0}]

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._detect_scenes_sync, video_path)

    def _detect_scenes_sync(self, video_path: str) -> List[Dict[str, Any]]:
        """Deteksi scene memakai `detect()`.

        Catatan: `VideoManager` sudah dihapus sejak PySceneDetect 0.7, sehingga
        implementasi lama selalu gagal import lalu jatuh ke fallback 60 detik.
        """
        from scenedetect import ContentDetector, detect

        scenes = detect(video_path, ContentDetector())
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
    ) -> str:
        """Bakar teks ke video dengan ffmpeg drawtext. Font sistem dilema dulu."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/Windows/Fonts/arialbd.ttf",
        ]
        font_file = next((p for p in font_paths if os.path.exists(p)), None)
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
        if box:
            drawtext += f":box=1:boxcolor={box_color}:boxborderw=8"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vf", drawtext,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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

    def _speaker_track_sync(
        self,
        input_path: str,
        start_time: float,
        duration: float,
        aspect_ratio: str,
        zoom: float,
        sample_fps: float,
        smooth: float,
    ) -> List[Tuple[float, float, float, float, float]]:
        """
        Deteksi wajah per sampel frame lalu bangun jalur crop.

        Mengembalikan (t_relatif, x, y, w, h) dalam piksel sumber. "Speaker" v1 =
        wajah terbesar yang stabil antar frame. Bila tidak ada wajah, daftar
        kosong (pemanggil memakai crop tengah).
        """
        import cv2

        num, den = aspect_ratio.replace(" ", "").split(":", 1)
        target_ratio = float(num) / float(den)
        zoom = max(1.0, float(zoom or 1.0))

        capture = cv2.VideoCapture(input_path)
        if not capture.isOpened():
            return []

        src_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        src_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
        if src_w <= 0 or src_h <= 0:
            capture.release()
            return []

        # YuNet butuh ukuran input yang tetap; buat setelah dimensi diketahui.
        detector = self._face_detector(src_w, src_h)
        if detector is None:
            capture.release()
            return []

        # Jendela crop: area terbesar yang muat, diperkecil sesuai zoom.
        if src_w / src_h > target_ratio:
            win_h = src_h / zoom
            win_w = win_h * target_ratio
        else:
            win_w = src_w / zoom
            win_h = win_w / target_ratio
        win_w = max(2, int(win_w) - int(win_w) % 2)
        win_h = max(2, int(win_h) - int(win_h) % 2)

        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_time) * 1000.0)
        step = max(1, int(round(fps / max(0.5, sample_fps))))
        total_frames = int(duration * fps)

        track: List[Tuple[float, float, float, float, float]] = []
        cx = src_w / 2.0
        cy = src_h / 2.0
        alive = True
        frame_index = 0

        while alive and frame_index <= total_frames:
            alive, frame = capture.read()
            if not alive or frame is None:
                break
            if frame_index % step == 0:
                # YuNet: faces = Nx15 [x, y, w, h, 5 landmark (x,y), score]
                detector.setInputSize((src_w, src_h))
                _, faces = detector.detect(frame)
                if faces is not None and len(faces) > 0:
                    fx, fy, fw, fh = max(
                        faces, key=lambda box: float(box[2]) * float(box[3])
                    )[:4]
                    target_x = float(fx) + float(fw) / 2.0
                    target_y = float(fy) + float(fh) / 2.0
                    # EMA: gerakan halus, tanpa jitter.
                    cx = (1 - smooth) * cx + smooth * target_x
                    cy = (1 - smooth) * cy + smooth * target_y

                x = min(max(0.0, cx - win_w / 2.0), src_w - win_w)
                y = min(max(0.0, cy - win_h / 2.0), src_h - win_h)
                track.append(
                    (
                        round(frame_index / fps, 3),
                        float(int(x) - int(x) % 2),
                        float(int(y) - int(y) % 2),
                        float(win_w),
                        float(win_h),
                    )
                )
            frame_index += 1

        capture.release()
        return track

    async def track_speaker_crop(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        aspect_ratio: str = "9:16",
        zoom: float = 1.0,
        filter_preset: Optional[str] = None,
        sample_fps: float = 2.5,
        smoothing: float = 0.35,
    ) -> str:
        """
        Render klip dengan jendela crop yang MENGIKUTI wajah pembicara
        (auto zoom follow-speaker).

        Posisi crop dianimasikan lewat `sendcmd` pada filter `crop` (opsi w/h/x/y
        ffmpeg bertanda `T` = mendukung timeline command), lalu di-scale ke
        resolusi target. Bila tidak ada wajah terdeteksi, kembali ke crop tengah.
        """
        width, height = self._dimensions_for_ratio(aspect_ratio)
        loop = asyncio.get_event_loop()

        track = await loop.run_in_executor(
            None,
            self._speaker_track_sync,
            input_path, start_time, duration, aspect_ratio, zoom, sample_fps, smoothing,
        )

        if not track:
            logger.warning("Track wajah kosong; memakai crop tengah: %s", input_path)
            return await self.render_clip(
                input_path, output_path,
                start_time=start_time, duration=duration,
                aspect_ratio=aspect_ratio, filter_preset=filter_preset,
            )

        _, first_x, first_y, win_w, win_h = track[0]

        # Format sendcmd: "<waktu> crop x <nilai>;" (waktu relatif terhadap klip).
        commands: List[str] = []
        for t_rel, x, y, _, _ in track:
            commands.append(f"{t_rel:.3f} crop x {x:.0f};")
            commands.append(f"{t_rel:.3f} crop y {y:.0f};")

        cmd_path = str(Path(output_path).with_name(f"track_{uuid4().hex}.cmd"))
        Path(cmd_path).write_text("\n".join(commands), encoding="utf-8")

        preset_chain = self.filter_chain_for_preset(filter_preset)
        chain = (
            f"sendcmd=f={self._escape_filter_path(cmd_path)},"
            f"crop=w={int(win_w)}:h={int(win_h)}:x={int(first_x)}:y={int(first_y)},"
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-r", str(settings.OUTPUT_FPS),
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        try:
            await loop.run_in_executor(None, self._run_ffmpeg, cmd)
        finally:
            try:
                os.remove(cmd_path)
            except OSError:
                pass
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "copy",
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
        vf_filter = f"subtitles=filename={self._escape_filter_path(subtitle_path)}"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
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
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
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
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                width = stream.get("width", 0)
                height = stream.get("height", 0)
                break
        
        return {
            "duration": duration,
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}",
        }