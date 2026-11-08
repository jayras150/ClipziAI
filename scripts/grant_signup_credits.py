"""
Grant signup bonus credits to users who don't have them yet.
Run: python scripts/grant_signup_credits.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.pricing_plan import PricingPlan
from app.models.credit_transaction import CreditTransaction, CreditTransactionType
from app.services.credit_service import CreditService


async def grant():
    async with AsyncSessionLocal() as session:
        # Get free plan
        result = await session.execute(
            __import__("sqlalchemy").select(PricingPlan).where(
                PricingPlan.name == "free"
            )
        )
        free_plan = result.scalar_one_or_none()
        
        if not free_plan:
            print("Free plan not found. Run seed_pricing.py first.")
            return
        
        # Find users without profiles
        result = await session.execute(
            __import__("sqlalchemy").select(User).where(
                ~User.id.in_(__import__("sqlalchemy").select(UserProfile.user_id))
            )
        )
        users = result.scalars().all()
        
        for user in users:
            profile = UserProfile(
                user_id=user.id,
                plan_type="free",
                credits_balance=5,
                credits_total_earned=5,
                max_concurrent_tasks=free_plan.max_concurrent_tasks,
                watermark_enabled=True,
            )
            session.add(profile)
            await session.flush()
            
            tx = CreditTransaction(
                user_id=user.id,
                amount=5,
                type=CreditTransactionType.SIGNUP_BONUS,
                description={"en": "Signup bonus", "id": "Bonus pendaftaran"},
                balance_after=5,
            )
            session.add(tx)
            print(f"Granted 5 credits to user {user.email}")
        
        await session.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(grant())