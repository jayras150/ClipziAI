"""
Pricing endpoints - List plans, subscribe
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.pricing_plan import PricingPlan
from app.schemas.pricing import PricingPlanResponse

router = APIRouter()


@router.get("/", response_model=list[PricingPlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(PricingPlan).where(PricingPlan.is_active == True))
    plans = result.scalars().all()
    return plans


@router.get("/{plan_id}", response_model=PricingPlanResponse)
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(PricingPlan).where(PricingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan