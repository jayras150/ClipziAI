"""
Webhook endpoints - Manage webhook subscriptions
"""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_current_user
from app.models.user import User
from app.schemas.webhook import WebhookSubscriptionCreate, WebhookSubscriptionResponse

router = APIRouter()


@router.post("/", response_model=WebhookSubscriptionResponse)
async def create_webhook(
    webhook_data: WebhookSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    # TODO: Create webhook subscription
    return WebhookSubscriptionResponse(
        id="placeholder",
        user_id=str(current_user.id),
        url=webhook_data.url,
        events=webhook_data.events,
        is_active=True,
        last_triggered_at=None,
        created_at=__import__("datetime").datetime.utcnow(),
    )


@router.get("/", response_model=List[WebhookSubscriptionResponse])
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    return []