"""
Payment schemas - Duitku integration
"""
from typing import Optional
from pydantic import BaseModel


class DuitkuPaymentRequest(BaseModel):
    amount: int  # IDR
    payment_method: Optional[str] = None
    order_id: str


class DuitkuPaymentResponse(BaseModel):
    payment_url: str
    transaction_id: str
    status: str


class DuitkuCallback(BaseModel):
    merchant_code: str
    payment_amount: str
    transaction_id: str
    result_code: str
    status: str
    signature: str


class DuitkuWebhook(BaseModel):
    merchant_code: str
    payment_amount: str
    transaction_id: str
    result_code: str
    status: str
    signature: str
    reference_id: Optional[str] = None