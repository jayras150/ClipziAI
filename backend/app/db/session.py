from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
# Import model modules before metadata creation. This is required for tables and
# string-based SQLAlchemy relationships to be registered in the same registry.
import app.models  # noqa: F401

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# async_sessionmaker menghasilkan AsyncSession yang benar (bukan Session biasa),
# sehingga `async with AsyncSessionLocal()` sah secara tipe maupun runtime.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables + migrasi kolom ringan yang idempoten.

    Repo ini memakai `create_all()` (tanpa Alembic untuk tabel baru). Untuk
    kolom baru pada tabel yang SUDAH ADA, `create_all()` tidak menambah apa pun,
    jadi kita jalankan `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (khusus
    PostgreSQL; SQLite dipakai di test dan tidak butuh migrasi ini).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if conn.dialect.name != "postgresql":
            return

        from sqlalchemy import text

        migrations = (
            ("download_status", "VARCHAR(24)"),
            ("error_category", "VARCHAR(40)"),
            ("user_message", "TEXT"),
            ("retry_count", "INTEGER DEFAULT 0"),
            ("max_retries", "INTEGER DEFAULT 3"),
            ("next_retry_at", "TIMESTAMPTZ"),
            ("source_asset_url", "TEXT"),
        )
        for column, ddl in migrations:
            await conn.execute(
                text(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {column} {ddl}")
            )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tasks_download_status "
                "ON tasks (download_status)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tasks_error_category "
                "ON tasks (error_category)"
            )
        )