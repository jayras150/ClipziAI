"""
Video Processor Service - FFmpeg, PySceneDetect, smart crop, burn subtitle
"""
import os
import asyncio
import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class VideoProcessor:
    """Process videos: scene detection, smart crop 9:16, burn subtitle, compress."""
    
    def __init__(self, work_dir: str = "./work"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    async def detect_scenes(self, video_path: str) -> List[Dict[str, Any]]:
        """Detect scene changes using PySceneDetect."""
        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._detect_scenes_sync, video_path
            )
        except ImportError:
            return [{"start": 0, "end": 60, "confidence": 1.0}]
    
    def _detect_scenes_sync(self, video_path: str) -> List[Dict[str, Any]]:
        from scenedetect import VideoManager, SceneManager
        from scenedetect.detectors import ContentDetector
        
        video_manager = VideoManager([video_path])
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        
        video_manager.start()
        scene_manager.detect_scenes(frame_source=video_manager)
        
        scene_list = scene_manager.get_scene_list()
        
        scenes = []
        for start_time, end_time in scene_list:
            scenes.append({
                "start": start_time.get_seconds(),
                "end": end_time.get_seconds(),
                "confidence": 1.0,
            })
        
        video_manager.release()
        return scenes
    
    async def smart_crop_9x16(
        self,
        input_path: str,
        output_path: str,
        start_time: float = 0,
        duration: float = 60,
        face_detect: bool = True,
    ) -> str:
        filter_complex = "crop=iw*9/16:ih"
        
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-ss", str(start_time),
            "-i", input_path,
            "-t", str(duration),
            "-vf", filter_complex,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-r", str(settings.OUTPUT_FPS),
            "-c:a", "aac", "-b:a", "128k",
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
        vf_filter = f"subtitles={subtitle_path}"
        
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

    async def get_video_info(self, video_path: str) -> Dict[str, Any]:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path,
        ]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, subprocess.run, cmd, subprocess.PIPE, subprocess.PIPE, True)
        
        import json
        data = json.loads(result.stdout)
        
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