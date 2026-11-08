"""
Credit endpoints - Credit history
"""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.schemas.credit import CreditTransactionResponse

router = APIRouter()


@router.get("/history", response_model=List[CreditTransactionResponse])
async def get_credit_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    limit: int = 50,
):
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == current_user.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    transactions = result.scalars().all()
    return transactions