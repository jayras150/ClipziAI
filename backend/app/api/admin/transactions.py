"""
Admin transactions: daftar dengan filter + total pendapatan.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.deps import get_current_admin
from app.api.deps import get_db_session
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(dependencies=[Depends(get_current_admin)])


@router.get("/")
async def list_transactions(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    q: Optional[str] = Query(default=None, description="Cari id transaksi / email user"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    query = select(Transaction, User.email).join(User, Transaction.user_id == User.id, isouter=True)
    if status_filter:
        query = query.where(Transaction.status == status_filter)
    if date_from:
        query = query.where(Transaction.created_at >= date_from)
    if date_to:
        query = query.where(Transaction.created_at <= date_to)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            func.coalesce(Transaction.duitku_transaction_id, "").ilike(like)
            | func.coalesce(User.email, "").ilike(like)
        )

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0

    sum_query = select(func.coalesce(func.sum(Transaction.amount), 0))
    if status_filter:
        sum_query = sum_query.where(Transaction.status == status_filter)
    if date_from:
        sum_query = sum_query.where(Transaction.created_at >= date_from)
    if date_to:
        sum_query = sum_query.where(Transaction.created_at <= date_to)
    grand_total = (await db.execute(sum_query)).scalar() or 0

    rows = (
        await db.execute(
            query.order_by(Transaction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return {
        "items": [
            {
                "id": str(t.id),
                "user_id": str(t.user_id),
                "user_email": email,
                "duitku_transaction_id": t.duitku_transaction_id,
                "amount": t.amount,
                "currency": t.currency,
                "status": getattr(t.status, "value", str(t.status)),
                "payment_method": t.payment_method,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t, email in rows
        ],
        "total": int(total),
        "total_amount": float(grand_total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/summary")
async def transactions_summary(db: AsyncSession = Depends(get_db_session)):
    """Ringkasan per status untuk kartu di dashboard."""
    rows = (
        await db.execute(
            select(Transaction.status, func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount), 0))
            .group_by(Transaction.status)
        )
    ).all()
    by_status = {
        getattr(status, "value", str(status)): {"count": int(count), "amount": float(amount)}
        for status, count, amount in rows
    }
    paid = by_status.get("paid", {"count": 0, "amount": 0.0})
    return {"by_status": by_status, "paid_count": paid["count"], "paid_amount": paid["amount"]}
