"""
YouTube endpoints - OAuth, upload, status
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from uuid import UUID

from app.api.deps import get_db_session, get_current_user
from app.core.config import get_settings
from app.core.security import encrypt_field
from app.models.user import User
from app.models.clip import Clip
from app.models.task import Task
from app.models.youtube_credential import YouTubeCredential
from app.schemas.youtube import (
    YouTubeAuthUrl,
    YouTubeConnectionStatus,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    ViralScoreResponse,
)
from app.services.youtube_service import YouTubeService
from app.services.viral import score_clip

router = APIRouter()
settings = get_settings()
youtube_service = YouTubeService()


def _create_oauth_state(user_id: UUID) -> str:
    """Create a short-lived, signed state that binds Google's callback to one user."""
    return jwt.encode(
        {
            "sub": str(user_id),
            "purpose": "youtube_oauth",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
        headers={"typ": "JWT"},
    )


def _decode_oauth_state(state: str) -> UUID:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "youtube_oauth" or not payload.get("sub"):
            raise ValueError("Invalid OAuth state purpose")
        return UUID(payload["sub"])
    except (JWTError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="State OAuth YouTube tidak valid atau sudah kedaluwarsa.") from exc


@router.get("/auth-url", response_model=YouTubeAuthUrl)
async def get_youtube_auth_url(current_user: User = Depends(get_current_user)):
    state = _create_oauth_state(current_user.id)
    auth_url = youtube_service.get_auth_url(state)

    # Cek konfigurasi ke Google dulu supaya pengguna tidak diarahkan ke halaman
    # error "redirect_uri_mismatch" tanpa penjelasan.
    problem = youtube_service.preflight(auth_url)
    if problem == "redirect_uri_mismatch":
        raise HTTPException(
            status_code=409,
            detail=(
                "Google menolak redirect URI "
                f"'{settings.YOUTUBE_REDIRECT_URI}'. Daftarkan URI tersebut di "
                "Google Cloud Console -> APIs & Services -> Credentials -> OAuth client "
                "-> Authorized redirect URIs, lalu coba lagi."
            ),
        )
    if problem == "invalid_client":
        raise HTTPException(
            status_code=409,
            detail=(
                "Google menolak client OAuth YouTube (invalid_client). Periksa "
                "YOUTUBE_CLIENT_ID dan YOUTUBE_CLIENT_SECRET di environment server."
            ),
        )

    return YouTubeAuthUrl(auth_url=auth_url)


@router.get("/diagnostics")
async def youtube_diagnostics(current_user: User = Depends(get_current_user)):
    """Ringkasan konfigurasi OAuth YouTube â€” dipakai halaman profil untuk status."""
    configured = bool(
        youtube_service.client_id and youtube_service.client_secret and youtube_service.redirect_uri
    )
    problem = None
    if configured:
        problem = youtube_service.preflight(youtube_service.get_auth_url("diagnostics"))

    return {
        "configured": configured,
        "client_id": youtube_service.client_id,
        # Client ID yang aman dipakai alur Google Identity Services (token flow)
        # karena origin https://<domain> sudah terdaftar sebagai Authorized
        # JavaScript origin. Biasanya ini client yang sama dengan tombol
        # "Continue with Google" (GOOGLE_CLIENT_ID).
        "gis_client_id": settings.GOOGLE_CLIENT_ID or youtube_service.client_id,
        "redirect_uri": youtube_service.redirect_uri,
        "reachable": problem is None,
        "problem": problem,
        "hint": {
            "redirect_uri_mismatch": (
                "Redirect URI belum terdaftar di Google Cloud Console "
                "(Authorized redirect URIs)."
            ),
            "invalid_client": "Client ID/secret OAuth Google salah atau sudah dihapus.",
            "network": "Server tidak bisa menghubungi Google saat memeriksa konfigurasi.",
        }.get(problem or "", None),
    }



@router.get("/callback", include_in_schema=False)
async def youtube_oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    """Finish Google OAuth, encrypt tokens, and return the user to the dashboard."""
    dashboard_url = settings.FRONTEND_URL.rstrip("/") + "/dashboard"
    if error:
        return RedirectResponse(f"{dashboard_url}?youtube=denied")
    if not code or not state:
        return RedirectResponse(f"{dashboard_url}?youtube=error")

    try:
        user_id = _decode_oauth_state(state)
        tokens = await youtube_service.exchange_code_for_tokens(code)
        channel = await youtube_service.get_channel(tokens["access_token"])
        existing = await db.execute(select(YouTubeCredential).where(YouTubeCredential.user_id == user_id))
        credential = existing.scalar_one_or_none()

        if credential is None:
            credential = YouTubeCredential(
                user_id=user_id,
                channel_id=channel["channel_id"],
                channel_name=channel["channel_name"],
                access_token_encrypted=encrypt_field(tokens["access_token"]),
                refresh_token_encrypted=encrypt_field(tokens.get("refresh_token", "")),
                token_expires_at=youtube_service.token_expiry(tokens.get("expires_in")),
                scopes="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
            )
            db.add(credential)
        else:
            credential.channel_id = channel["channel_id"]
            credential.channel_name = channel["channel_name"]
            credential.access_token_encrypted = encrypt_field(tokens["access_token"])
            if tokens.get("refresh_token"):
                credential.refresh_token_encrypted = encrypt_field(tokens["refresh_token"])
            credential.token_expires_at = youtube_service.token_expiry(tokens.get("expires_in"))

        await db.commit()
        return RedirectResponse(f"{dashboard_url}?youtube=connected")
    except HTTPException:
        await db.rollback()
        return RedirectResponse(f"{dashboard_url}?youtube=error")
    except Exception:
        await db.rollback()
        return RedirectResponse(f"{dashboard_url}?youtube=error")


class YouTubeTokenPayload(BaseModel):
    """Access token dari Google Identity Services (alur tanpa redirect URI)."""

    access_token: str


@router.post("/token", response_model=YouTubeConnectionStatus)
async def connect_youtube_with_token(
    payload: YouTubeTokenPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Hubungkan YouTube memakai access token dari Google Identity Services.

    Dipakai sebagai fallback ketika redirect URI server belum terdaftar di
    Google Cloud Console: alur ini tidak memerlukan redirect URI sama sekali,
    hanya JavaScript origin yang juga dipakai tombol "Sign in with Google".
    """
    access_token = (payload.access_token or "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token Google tidak boleh kosong.")

    channel = await youtube_service.get_channel(access_token)

    result = await db.execute(select(YouTubeCredential).where(YouTubeCredential.user_id == current_user.id))
    credential = result.scalar_one_or_none()
    encrypted_token = encrypt_field(access_token)

    if credential is None:
        credential = YouTubeCredential(
            user_id=current_user.id,
            channel_id=channel["channel_id"],
            channel_name=channel["channel_name"],
            access_token_encrypted=encrypted_token,
            refresh_token_encrypted=encrypt_field(""),
            token_expires_at=youtube_service.token_expiry(3600),
            scopes="https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        )
        db.add(credential)
    else:
        credential.channel_id = channel["channel_id"]
        credential.channel_name = channel["channel_name"]
        credential.access_token_encrypted = encrypted_token
        credential.token_expires_at = youtube_service.token_expiry(3600)

    await db.commit()

    return YouTubeConnectionStatus(
        connected=True,
        channel_id=channel["channel_id"],
        channel_name=channel["channel_name"],
        message="Akun YouTube terhubung.",
    )


@router.get("/status", response_model=YouTubeConnectionStatus)
async def get_youtube_connection_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(YouTubeCredential).where(YouTubeCredential.user_id == current_user.id))
    credential = result.scalar_one_or_none()
    if credential is None:
        return YouTubeConnectionStatus(connected=False, message="Akun YouTube belum terhubung.")
    return YouTubeConnectionStatus(
        connected=True,
        channel_id=credential.channel_id,
        channel_name=credential.channel_name,
        message="Akun YouTube terhubung.",
    )


@router.delete("/disconnect", response_model=YouTubeConnectionStatus)
async def disconnect_youtube(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(select(YouTubeCredential).where(YouTubeCredential.user_id == current_user.id))
    credential = result.scalar_one_or_none()
    if credential:
        await db.delete(credential)
        await db.commit()
    return YouTubeConnectionStatus(connected=False, message="Koneksi akun YouTube dihapus dari Clipzi AI.")


@router.post("/upload", response_model=YouTubeUploadResponse)
async def upload_to_youtube(
    upload_data: YouTubeUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Implement YouTube Data API v3 upload
    return YouTubeUploadResponse(
        success=False,
        error="YouTube upload not yet implemented",
    )


@router.get("/viral-score/{clip_id}", response_model=ViralScoreResponse)
async def get_viral_score(
    clip_id: str,
    force: bool = Query(False, description="Hitung ulang walau skor sudah tersimpan"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Skor viral satu klip.

    Disimpan di `clips.viral_score` / `viral_factors` agar dashboard tidak
    menghitung ulang tiap render. `force=true` memaksa hitung ulang (tombol â†»).
    """
    try:
        cid = UUID(clip_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid clip id")

    result = await db.execute(
        select(Clip)
        .join(Task, Clip.task_id == Task.id)
        .where(Clip.id == cid, Task.user_id == current_user.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if force or clip.viral_score is None:
        # Transkrip per klip tidak disimpan di DB, jadi pakai estimasi metadata.
        payload = score_clip(
            transcript="",
            duration=float(clip.duration or 0),
            has_subtitle=bool(clip.subtitle_url),
            has_caption=bool(clip.editing_applied),
            estimated=clip.viral_score is None and not force,
        )
        clip.viral_score = payload["score"]
        clip.viral_factors = payload["factors"]
        await db.commit()

    factors = dict(clip.viral_factors or {})
    tags = list(clip.ai_suggested_tags or [])
    return ViralScoreResponse(
        clip_id=str(clip.id),
        score=float(clip.viral_score or 0),
        factors=factors,
        recommended_title=clip.ai_suggested_title or clip.title or "Clip",
        recommended_tags=tags or ["shorts", "viral"],
        reasoning=str(factors.get("reasoning") or ""),
    )
