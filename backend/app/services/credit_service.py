"""
Credit Service - Credit management: signup bonus, deduct, refund, top-up
"""
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user_profile import UserProfile
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.core.feature_gate import FeatureGate

class CreditService:
    """Manage user credits."""
    
    @staticmethod
    async def grant_signup_bonus(
        db: AsyncSession,
        user_id: str,
        amount: int = 5,
    ) -> int:
        """Grant signup bonus credits to new user."""
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        
        if not profile:
            return 0
        
        profile.credits_balance += amount
        profile.credits_total_earned += amount
        
        tx = CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=CreditTransactionType.SIGNUP_BONUS,
            description={"en": "Signup bonus", "id": "Bonus pendaftaran"},
            balance_after=profile.credits_balance,
        )
        db.add(tx)
        await db.commit()
        
        return profile.credits_balance
    
    @staticmethod
    async def deduct_credits(
        db: AsyncSession,
        user_id: str,
        amount: float,
        description: dict,
        task_id: Optional[str] = None,
    ) -> int:
        """Deduct credits from user balance."""
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        
        if not profile or profile.credits_balance < amount:
            raise ValueError("Insufficient credits")
        
        profile.credits_balance -= int(amount)
        profile.credits_total_spent += int(amount)
        
        tx = CreditTransaction(
            user_id=user_id,
            amount=-int(amount),
            type=CreditTransactionType.TASK_SPENT,
            description=description,
            task_id=task_id,
            balance_after=profile.credits_balance,
        )
        db.add(tx)
        await db.commit()
        
        return profile.credits_balance
    
    @staticmethod
    async def add_credits(
        db: AsyncSession,
        user_id: str,
        amount: int,
        description: dict,
    ) -> int:
        """Add credits (e.g., from subscription purchase)."""
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        
        if not profile:
            return 0
        
        profile.credits_balance += amount
        profile.credits_total_earned += amount
        
        tx = CreditTransaction(
            user_id=user_id,
            amount=amount,
            type=CreditTransactionType.PURCHASE,
            description=description,
            balance_after=profile.credits_balance,
        )
        db.add(tx)
        await db.commit()
        
        return profile.credits_balance
    
    @staticmethod
    async def get_balance(db: AsyncSession, user_id: str) -> int:
        """Get current credit balance."""
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        return profile.credits_balance if profile else 0