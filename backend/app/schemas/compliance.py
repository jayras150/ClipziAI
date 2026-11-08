"""
Compliance schemas - Copyright, moderation, GDPR, invoice
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class CopyrightCheckResponse(BaseModel):
    id: str
    task_id: str
    content_type: str
    status: str
    detected_source: Optional[str]
    confidence_score: Optional[float]
    action_taken: str
    checked_at: datetime

    class Config:
        from_attributes = True


class ContentModerationResponse(BaseModel):
    id: str
    task_id: str
    status: str
    flags: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class GDPRRequestCreate(BaseModel):
    request_type: str  # data_export, data_deletion, account_deletion


class GDPRRequestResponse(BaseModel):
    id: str
    user_id: str
    request_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    amount: int
    tax_amount: int
    total_amount: int
    status: str
    pdf_url: Optional[str]
    issued_at: datetime

    class Config:
        from_attributes = True