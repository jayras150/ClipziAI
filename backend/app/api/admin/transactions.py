"""
Admin transaction monitoring endpoints
"""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db_session
from app.models.transaction import Transaction

router = APIRouter()


@router.get("/", response_model=List[dict])
async def list_transactions(
    db: AsyncSession = Depends(get_db_session),
    limit: int = 100,
):
    result = await db.execute(
        select(Transaction).order_by(Transaction.created_at.desc()).limit(limit)
    )
    transactions = result.scalars().all()
    
    return [
        {
            "id": str(t.id),
            "user_id": str(t.user_id),
            "duitku_transaction_id": t.duitku_transaction_id,
            "amount": t.amount,
            "status": t.status.value,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in transactions
    ]