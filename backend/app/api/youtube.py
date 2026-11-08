"""
YouTube endpoints - OAuth, upload, status
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from uuid import UUID

from app.api.deps import get_db_session, get_current_user
from app.core.config import get_settings
from app.core.security import encrypt_field
from app.models.user import User
from app.models.youtube_credential import YouTubeCredential
from app.schemas.youtube import (
    YouTubeAuthUrl,
    YouTubeConnectionStatus,
    YouTubeUploadRequest,
    YouTubeUploadResponse,
    ViralScoreResponse,
)
from app.services.youtube_service import YouTubeService

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
    return YouTubeAuthUrl(auth_url=youtube_service.get_auth_url(state))


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Implement AI viral scoring
    return ViralScoreResponse(
        clip_id=clip_id,
        score=75.0,
        factors={"hook_strength": 0.8, "retention_potential": 0.7},
        recommended_title="Viral Clip Title",
        recommended_tags=["viral", "shorts"],
        reasoning="Strong hook and good retention potential",
    )