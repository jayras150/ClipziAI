"""
Clipzi AI - FastAPI Application Entry Point
"""
import asyncio
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
from app.api.admin import ai as admin_ai
from app.api.admin import branding as admin_branding
from app.api.admin import platform as admin_platform
from app.api.admin import proxies as admin_proxies
from app.api.admin import storage as admin_storage
from app.api import branding as public_branding
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
    # Pemeliharaan instance Vast (hapus yatim + lanjutkan pemantauan) dilakukan
    # di BACKGROUND dengan batas waktu. Panggilan jaringan ke Vast tidak boleh
    # menahan startup API: kalau console.vast.ai lambat, dulu seluruh API ikut
    # menggantung (healthcheck 502) sampai panggilan itu selesai.
    async def _vast_maintenance() -> None:
        from app.services.vast_worker import cleanup_orphan_instances, resume_supervisors

        removed = await cleanup_orphan_instances()
        if removed:
            logger.warning("%s instance Vast.ai yatim dihapus saat startup", removed)
        resumed = await resume_supervisors()
        if resumed:
            logger.warning("%s instance Vast.ai dilanjutkan pemantauannya", resumed)

    async def _run_vast_maintenance() -> None:
        try:
            await asyncio.wait_for(_vast_maintenance(), timeout=120)
        except Exception as exc:  # jangan gagalkan startup karena Vast
            logger.warning("Pemeliharaan instance Vast gagal/dilewati: %s", exc)

    asyncio.create_task(_run_vast_maintenance())
    # Setelan AI tersimpan di DB -> inject ke env/settings saat startup supaya
    # kredensial dari dashboard langsung dipakai tanpa menunggu request admin.
    try:
        from app.services.ai_config import load_and_apply_ai_config

        await load_and_apply_ai_config()
    except Exception as exc:
        logger.warning("Gagal memuat setelan AI dari database: %s", exc)
    # Setelan ekosistem (domain publik/admin, support email, maintenance) juga
    # disimpan di DB supaya ganti domain tidak perlu rebuild/restart.
    try:
        from app.services.platform_config import load_and_apply_platform_config

        await load_and_apply_platform_config()
    except Exception as exc:
        logger.warning("Gagal memuat setelan platform dari database: %s", exc)
    # Registry storage multi-provider (R2/B2/S3/...). Bila belum ada, otomatis
    # dibuat dari env R2_* agar deployment lama tetap jalan.
    try:
        from app.services.storage_registry import load_storage_config

        await load_storage_config()
    except Exception as exc:
        logger.warning("Gagal memuat konfigurasi storage: %s", exc)
    # Pool proxy YouTube (hasil filter aktif) dipakai otomatis oleh downloader.
    try:
        from app.services.proxy_pool import load_and_apply_proxy_pool

        await load_and_apply_proxy_pool()
    except Exception as exc:
        logger.warning("Gagal memuat pool proxy dari database: %s", exc)
    yield
    # Shutdown
    await engine.dispose()


# Dokumentasi API hanya aktif saat DEBUG: di produksi /docs, /redoc, dan
# /openapi.json dimatikan supaya peta endpoint tidak bisa dipanen publik.
_DOCS_ENABLED = bool(getattr(settings, "DEBUG", False))

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Clipzi AI - Turn Long Videos into Viral Shorts",
    lifespan=lifespan,
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def dynamic_origin_cors(request, call_next):
    """
    CORS untuk origin yang diatur dari dashboard (domain publik/admin).

    `CORSMiddleware` di atas hanya mengenal origin dari env saat container
    start. Supaya ganti domain langsung berlaku, origin dari setelan platform
    ditangani di sini (daftar `EXTRA_ORIGINS` diperbarui saat setelan disimpan
    atau saat startup).
    """
    from starlette.responses import Response

    from app.services.platform_config import EXTRA_ORIGINS

    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") in [item.rstrip("/") for item in EXTRA_ORIGINS]:
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "*",
                    "Access-Control-Allow-Headers": request.headers.get(
                        "access-control-request-headers", "*"
                    ),
                    "Access-Control-Max-Age": "600",
                },
            )
        response = await call_next(request)
        if "access-control-allow-origin" not in {
            key.lower() for key in response.headers.keys()
        }:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    return await call_next(request)

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
app.include_router(admin_ai.router, prefix="/api/admin/settings", tags=["Admin AI Settings"])
app.include_router(
    admin_platform.router, prefix="/api/admin/settings", tags=["Admin Platform Settings"]
)
app.include_router(
    admin_proxies.router, prefix="/api/admin/settings/proxies", tags=["Admin Proxy Pool"]
)
app.include_router(
    admin_storage.router, prefix="/api/admin/settings/storage", tags=["Admin Storage"]
)
app.include_router(
    admin_branding.router, prefix="/api/admin/settings", tags=["Admin Branding"]
)
app.include_router(public_branding.router, prefix="/api", tags=["Branding"])
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