"""
Admin pricing plan management: list, create, update, delete.
"""
from typing import List

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.pricing_plan import PricingPlan
from app.schemas.pricing import PricingPlanResponse

router = APIRouter(dependencies=[Depends(get_current_admin)])

PLAN_NAMES = ("free", "standar", "pro", "team")


class PlanIn(BaseModel):
    name: str = Field(description="free | standar | pro | team")
    display_name: dict = Field(default_factory=lambda: {"en": "", "id": ""})
    description: dict = Field(default_factory=lambda: {"en": "", "id": ""})
    price_monthly: int = 0
    price_yearly: int = 0
    credits_monthly: int = 0
    max_video_duration_minutes: int = 60
    max_concurrent_tasks: int = 1
    watermark: bool = True
    priority_queue: bool = False
    youtube_upload: bool = False
    all_editing_features: bool = False
    team_seats: int = 1
    features_list: List[str] = Field(default_factory=list)
    is_active: bool = True


def _validate_name(name: str) -> str:
    value = (name or "").strip().lower()
    if value not in PLAN_NAMES:
        raise HTTPException(status_code=400, detail=f"Plan harus salah satu: {', '.join(PLAN_NAMES)}")
    return value


@router.get("/", response_model=List[PricingPlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(PricingPlan).order_by(PricingPlan.price_monthly))
    return result.scalars().all()


@router.post("/", response_model=PricingPlanResponse)
async def create_plan(plan_data: PlanIn, db: AsyncSession = Depends(get_db_session)):
    name = _validate_name(plan_data.name)
    existing = (
        await db.execute(select(PricingPlan).where(PricingPlan.name == name))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Plan dengan nama itu sudah ada")

    plan = PricingPlan(**{**plan_data.model_dump(), "name": name})
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.put("/{plan_id}", response_model=PricingPlanResponse)
async def update_plan(
    plan_id: UUID,
    plan_data: PlanIn,
    db: AsyncSession = Depends(get_db_session),
):
    plan = (await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan tidak ditemukan")

    payload = plan_data.model_dump()
    payload["name"] = _validate_name(payload["name"])
    for key, value in payload.items():
        setattr(plan, key, value)

    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=204)
async def delete_plan(plan_id: UUID, db: AsyncSession = Depends(get_db_session)):
    plan = (await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan tidak ditemukan")
    await db.delete(plan)
    await db.commit()
    return None
