"""
Seed pricing plans into the database.
Run: python scripts/seed_pricing.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.models.pricing_plan import PricingPlan

PRICING_PLANS = [
    {
        "name": "free",
        "display_name": {"id": "Gratis", "en": "Free"},
        "description": {"id": "Untuk mencoba fitur dasar", "en": "For trying basic features"},
        "price_monthly": 0,
        "price_yearly": 0,
        "credits_monthly": 5,
        "max_video_duration_minutes": 5,
        "max_concurrent_tasks": 1,
        "watermark": True,
        "priority_queue": False,
        "youtube_upload": False,
        "all_editing_features": False,
        "team_seats": 1,
        "features_list": ["smart_crop_9x16", "auto_subtitle"],
        "is_active": True,
    },
    {
        "name": "standar",
        "display_name": {"id": "Standar", "en": "Standar"},
        "description": {"id": "Untuk kreator pemula", "en": "For beginner creators"},
        "price_monthly": 99000,
        "price_yearly": 990000,
        "credits_monthly": 30,
        "max_video_duration_minutes": 30,
        "max_concurrent_tasks": 2,
        "watermark": False,
        "priority_queue": False,
        "youtube_upload": True,
        "all_editing_features": False,
        "team_seats": 1,
        "features_list": [
            "smart_crop_9x16", "auto_subtitle", "contrast_brightness",
            "auto_zoom_face", "auto_zoom_audio", "blur_background",
            "karaoke_subtitle", "silence_removal", "background_music",
            "title_card", "progress_bar", "youtube_upload",
        ],
        "is_active": True,
    },
    {
        "name": "pro",
        "display_name": {"id": "Pro", "en": "Pro"},
        "description": {"id": "Untuk kreator profesional", "en": "For professional creators"},
        "price_monthly": 249000,
        "price_yearly": 2490000,
        "credits_monthly": 100,
        "max_video_duration_minutes": 60,
        "max_concurrent_tasks": 5,
        "watermark": False,
        "priority_queue": True,
        "youtube_upload": True,
        "all_editing_features": True,
        "team_seats": 1,
        "features_list": [
            "smart_crop_9x16", "auto_subtitle", "contrast_brightness",
            "auto_zoom_face", "auto_zoom_audio", "blur_background",
            "karaoke_subtitle", "silence_removal", "background_music",
            "title_card", "progress_bar", "youtube_upload",
            "object_tracking", "ken_burns", "animated_caption",
            "multi_language_subtitle", "audio_ducking", "noise_reduction",
            "voice_enhancement", "sound_effects", "color_grading",
            "video_filters", "speed_ramp", "transitions",
            "custom_watermark", "sticker_overlay", "intro_outro",
            "end_screen", "viral_scoring", "ai_metadata", "thumbnail_ai",
        ],
        "is_active": True,
    },
    {
        "name": "team",
        "display_name": {"id": "Team", "en": "Team"},
        "description": {"id": "Untuk tim dan agency", "en": "For teams and agencies"},
        "price_monthly": 499000,
        "price_yearly": 4990000,
        "credits_monthly": 300,
        "max_video_duration_minutes": 120,
        "max_concurrent_tasks": 10,
        "watermark": False,
        "priority_queue": True,
        "youtube_upload": True,
        "all_editing_features": True,
        "team_seats": 5,
        "features_list": [
            "smart_crop_9x16", "auto_subtitle", "contrast_brightness",
            "auto_zoom_face", "auto_zoom_audio", "blur_background",
            "karaoke_subtitle", "silence_removal", "background_music",
            "title_card", "progress_bar", "youtube_upload",
            "object_tracking", "ken_burns", "animated_caption",
            "multi_language_subtitle", "audio_ducking", "noise_reduction",
            "voice_enhancement", "sound_effects", "color_grading",
            "video_filters", "speed_ramp", "transitions",
            "custom_watermark", "sticker_overlay", "intro_outro",
            "end_screen", "viral_scoring", "ai_metadata", "thumbnail_ai",
        ],
        "is_active": True,
    },
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        for plan_data in PRICING_PLANS:
            existing = await session.execute(
                __import__("sqlalchemy").select(PricingPlan).where(
                    PricingPlan.name == plan_data["name"]
                )
            )
            if existing.scalar_one_or_none():
                print(f"Plan '{plan_data['name']}' already exists, skipping.")
                continue
            
            plan = PricingPlan(**plan_data)
            session.add(plan)
            print(f"Created plan: {plan_data['name']}")
        
        await session.commit()
        print("Pricing plans seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed())