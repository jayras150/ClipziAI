"""
Seed harga plan (idempotent).

Dipakai sekali setelah deploy supaya halaman Pricing publik dan dashboard admin
(Plans) punya data. Jalankan di container API:

    docker exec -w /app clipzi-api /opt/venv/bin/python -m scripts.seed_pricing

Aman diulang: plan yang sudah ada akan diperbarui, bukan diduplikasi.
"""
import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, init_db
from app.models.pricing_plan import PricingPlan

PLANS = [
    {
        "name": "free",
        "display_name": {"en": "Free", "id": "Gratis"},
        "description": {
            "en": "Try ClipzyAI with limited credits.",
            "id": "Coba ClipzyAI dengan kredit terbatas.",
        },
        "price_monthly": 0,
        "price_yearly": 0,
        "credits_monthly": 30,
        "max_video_duration_minutes": 30,
        "max_concurrent_tasks": 1,
        "watermark": True,
        "priority_queue": False,
        "youtube_upload": False,
        "all_editing_features": False,
        "team_seats": 1,
        "features_list": ["9:16 smart crop", "Auto subtitle", "Watermark Clipzy"],
        "is_active": True,
    },
    {
        "name": "standar",
        "display_name": {"en": "Standard", "id": "Standar"},
        "description": {
            "en": "For creators publishing every week.",
            "id": "Untuk kreator yang publish tiap minggu.",
        },
        "price_monthly": 99000,
        "price_yearly": 990000,
        "credits_monthly": 150,
        "max_video_duration_minutes": 90,
        "max_concurrent_tasks": 2,
        "watermark": False,
        "priority_queue": False,
        "youtube_upload": True,
        "all_editing_features": False,
        "team_seats": 1,
        "features_list": ["Tanpa watermark", "Upload YouTube", "Prioritas normal"],
        "is_active": True,
    },
    {
        "name": "pro",
        "display_name": {"en": "Pro", "id": "Pro"},
        "description": {
            "en": "Daily clipping with AI metadata and priority queue.",
            "id": "Clipping harian dengan metadata AI dan antrean prioritas.",
        },
        "price_monthly": 249000,
        "price_yearly": 2490000,
        "credits_monthly": 500,
        "max_video_duration_minutes": 180,
        "max_concurrent_tasks": 3,
        "watermark": False,
        "priority_queue": True,
        "youtube_upload": True,
        "all_editing_features": True,
        "team_seats": 1,
        "features_list": [
            "Semua fitur editing",
            "Metadata AI",
            "Antrean prioritas",
            "Klip lebih banyak",
        ],
        "is_active": True,
    },
    {
        "name": "team",
        "display_name": {"en": "Team", "id": "Tim"},
        "description": {
            "en": "Shared credits and seats for agencies.",
            "id": "Kredit & kursi bersama untuk agensi.",
        },
        "price_monthly": 699000,
        "price_yearly": 6990000,
        "credits_monthly": 1500,
        "max_video_duration_minutes": 240,
        "max_concurrent_tasks": 5,
        "watermark": False,
        "priority_queue": True,
        "youtube_upload": True,
        "all_editing_features": True,
        "team_seats": 5,
        "features_list": ["5 kursi tim", "Kredit bersama", "Antrean prioritas", "Dukungan prioritas"],
        "is_active": True,
    },
]


async def seed() -> None:
    await init_db()
    created = 0
    updated = 0
    async with AsyncSessionLocal() as db:
        for payload in PLANS:
            existing = (
                await db.execute(select(PricingPlan).where(PricingPlan.name == payload["name"]))
            ).scalar_one_or_none()
            if existing is None:
                db.add(PricingPlan(**payload))
                created += 1
            else:
                for key, value in payload.items():
                    setattr(existing, key, value)
                updated += 1
        await db.commit()
    print(f"seed_pricing selesai: {created} dibuat, {updated} diperbarui")


if __name__ == "__main__":
    asyncio.run(seed())
