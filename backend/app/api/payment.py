"""
Payment endpoints - Duitku integration
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import uuid4

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.models.transaction import Transaction, TransactionStatus
from app.models.user_profile import UserProfile
from app.schemas.payment import DuitkuPaymentRequest, DuitkuPaymentResponse, DuitkuCallback
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/create", response_model=DuitkuPaymentResponse)
async def create_payment(
    payment_data: DuitkuPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # Create transaction record
    transaction = Transaction(
        user_id=current_user.id,
        duitku_transaction_id=payment_data.order_id,
        amount=payment_data.amount,
        status=TransactionStatus.PENDING,
        payment_method=payment_data.payment_method,
    )
    db.add(transaction)
    await db.commit()
    
    # In production, call Duitku API to get payment URL
    # For now, return a mock payment URL
    payment_url = f"https://sandbox.duitku.com/webview/payment/{payment_data.order_id}"
    
    return DuitkuPaymentResponse(
        payment_url=payment_url,
        transaction_id=payment_data.order_id,
        status="pending",
    )


@router.post("/callback")
async def duitku_callback(callback: DuitkuCallback, request: Request, db: AsyncSession = Depends(get_db_session)):
    # TODO: Verify Duitku signature
    # Update transaction status
    result = await db.execute(
        select(Transaction).where(Transaction.duitku_transaction_id == callback.transaction_id)
    )
    transaction = result.scalar_one_or_none()
    
    if transaction:
        transaction.status = TransactionStatus.SUCCESS if callback.status == "success" else TransactionStatus.FAILED
        transaction.callback_received_at = __import__("datetime").datetime.utcnow()
        await db.commit()
    
    return {"received": True}