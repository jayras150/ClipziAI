"""Endpoint publik: branding yang dipakai frontend (logo, favicon, nama)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.branding import get_branding

router = APIRouter()


@router.get("/branding")
async def public_branding(db: AsyncSession = Depends(get_db_session)):
    return await get_branding(db)
