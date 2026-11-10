"""
Admin pricing plan management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.pricing_plan import PricingPlan
from app.schemas.pricing import PricingPlanResponse

from app.api.admin.deps import get_current_admin  # noqa: E402

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/", response_model=List[PricingPlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(PricingPlan))
    plans = result.scalars().all()
    return plans


@router.post("/", response_model=PricingPlanResponse)
async def create_plan(plan_data: dict, db: AsyncSession = Depends(get_db_session)):
    # TODO: Implement full plan creation with validation
    plan = PricingPlan(**plan_data)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan