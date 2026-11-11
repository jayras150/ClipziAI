"""
Clipzi AI - FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import engine, init_db
from app.api import tasks, health, formats, editing, youtube, clips, internal
from app.api import auth, users, pricing, payment, credits
from app.api import music
from app.api.admin import auth as admin_auth
from app.api.admin import users as admin_users
from app.api.admin import plans as admin_plans
from app.api.admin import tasks as admin_tasks
from app.api.admin import transactions as admin_transactions
from app.api.admin import audit as admin_audit
from app.api.admin import system as admin_system
from app.api.admin import security as admin_security
from app.api.admin import ytdlp_cookies as admin_ytdlp_cookies
from app.api.admin import settings as admin_settings
from app.api.admin import youtube as admin_youtube
from app.api.admin import workers as admin_workers
from app.api import multi_platform, clip_templates, bulk_jobs, analytics
from app.api import api_keys, webhooks, compliance
from app.api import scheduled_publish

settings = get_settings()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Bersihkan instance GPU yatim (mode `oneshot`) yang tertinggal karena
    # restart/crash: reaper di memori hilang, tapi instance tetap ditagih.
    try:
        from app.services.vast_worker import cleanup_orphan_instances

        removed = await cleanup_orphan_instances()
        if removed:
            logger.warning("%s instance Vast.ai yatim dihapus saat startup", removed)
    except Exception as exc:  # jangan gagalkan startup karena Vast
        logger.warning("Pemeriksaan instance yatim gagal: %s", exc)
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Clipzi AI - Turn Long Videos into Viral Shorts",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers - Public API
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(pricing.router, prefix="/api/pricing", tags=["Pricing"])
app.include_router(payment.router, prefix="/api/payment", tags=["Payment"])
app.include_router(credits.router, prefix="/api/credits", tags=["Credits"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(clips.router, prefix="/api/clips", tags=["Clips"])
app.include_router(internal.router, prefix="/api/internal", tags=["Internal"])
app.include_router(music.router, prefix="/api/music", tags=["Music"])
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(formats.router, prefix="/api", tags=["Formats"])
app.include_router(editing.router, prefix="/api/editing", tags=["Editing"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["YouTube"])
app.include_router(multi_platform.router, prefix="/api/multi-platform", tags=["Multi-Platform"])
app.include_router(clip_templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(bulk_jobs.router, prefix="/api/bulk", tags=["Bulk Jobs"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["API Keys"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["Compliance"])
app.include_router(scheduled_publish.router, prefix="/api/scheduled-publish", tags=["Scheduled Publish"])

# Routers - Admin API
app.include_router(admin_auth.router, prefix="/api/admin/auth", tags=["Admin Auth"])
app.include_router(admin_users.router, prefix="/api/admin/users", tags=["Admin Users"])
app.include_router(admin_plans.router, prefix="/api/admin/plans", tags=["Admin Plans"])
app.include_router(admin_tasks.router, prefix="/api/admin/tasks", tags=["Admin Tasks"])
app.include_router(admin_transactions.router, prefix="/api/admin/transactions", tags=["Admin Transactions"])
app.include_router(admin_audit.router, prefix="/api/admin/audit", tags=["Admin Audit"])
app.include_router(admin_system.router, prefix="/api/admin/system", tags=["Admin System"])
app.include_router(admin_security.router, prefix="/api/admin/security", tags=["Admin Security"])
app.include_router(admin_settings.router, prefix="/api/admin/settings", tags=["Admin Settings"])
app.include_router(admin_youtube.router, prefix="/api/admin/youtube", tags=["Admin YouTube"])
app.include_router(admin_workers.router, prefix="/api/admin/workers", tags=["Admin Workers"])
app.include_router(
    admin_ytdlp_cookies.router,
    prefix="/api/admin/ytdlp-cookies",
    tags=["Admin yt-dlp Cookies"],
)


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }