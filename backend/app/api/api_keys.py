"""
API Key endpoints - Manage user API keys
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.api_key import APIKeyCreate, APIKeyResponse, APIKeyRawResponse

router = APIRouter()


@router.post("/", response_model=APIKeyRawResponse)
async def create_api_key(
    key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Create API key in DB
    return APIKeyRawResponse(
        raw_key="clipzy_" + "x" * 32,
        key_prefix="clipzy_xxxx",
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return []