"""
Video Processor Service - FFmpeg, PySceneDetect, smart crop, burn subtitle
"""
import os
import asyncio
import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings

settings = get_settings()


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

    @staticmethod
    def _escape_filter_path(path: str) -> str:
        """Escape path agar aman sebagai opsi filter ffmpeg."""
        text = str(path).replace("\\", "/")
        text = text.replace(":", r"\:").replace("'", r"\'")
        return f"'{text}'"

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
        min_silence_duration: float = 1.0,
    ) -> str:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-i", input_path,
            "-af", f"silenceremove=start_periods=1:start_duration={min_silence_duration}:start_threshold=-50dB:detection=peak",
            "-c:v", "copy",
            output_path,
        ]
        
        loop = asyncio.get_event_loop()
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