"""
Music library — daftar musik latar yang bisa dipakai saat editing klip.

Track disimpan di R2 (`assets/music/...`) dan didaftarkan di berkas
`app/assets/music_library.json`. Endpoint ini hanya mengembalikan metadata
(nama, mood, URL publik) — tidak ada file yang disimpan di server VPS.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "assets" / "music_library.json"


def _load_manifest() -> Dict[str, Any]:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Manifest musik tidak ditemukan: %s", MANIFEST_PATH)
        return {"tracks": []}
    except json.JSONDecodeError as exc:
        logger.error("Manifest musik rusak: %s", exc)
        return {"tracks": []}


@router.get("")
async def list_music_library(current_user: User = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """Daftar track musik latar yang tersedia untuk semua pengguna."""
    tracks = _load_manifest().get("tracks") or []
    return [
        {
            "id": track.get("id"),
            "name": track.get("name"),
            "mood": track.get("mood"),
            "duration": track.get("duration"),
            "url": track.get("url"),
        }
        for track in tracks
        if track.get("url")
    ]


@router.get("/{track_id}")
async def get_music_track(
    track_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Detail satu track (dipakai untuk preview durasi di UI)."""
    for track in _load_manifest().get("tracks") or []:
        if str(track.get("id")) == track_id:
            return track
    raise HTTPException(status_code=404, detail="Track not found")
