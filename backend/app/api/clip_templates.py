"""
Clip template endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.clip_template import ClipTemplateCreate, ClipTemplateResponse

router = APIRouter()


@router.post("/", response_model=ClipTemplateResponse)
async def create_template(
    template_data: ClipTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Save template to DB
    return ClipTemplateResponse(
        id="placeholder",
        user_id=str(current_user.id),
        name=template_data.name,
        description=template_data.description,
        editing_options=template_data.editing_options,
        is_public=False,
        usage_count=0,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/", response_model=List[ClipTemplateResponse])
async def list_templates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Fetch from DB
    return []