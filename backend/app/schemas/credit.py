"""
Credit schemas - Credit transactions
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class CreditTransactionResponse(BaseModel):
    id: str
    amount: int
    type: str
    description: Optional[dict]
    balance_after: int
    created_at: datetime

    class Config:
        from_attributes = True