"""
Redis client helper - works with Upstash (rediss:// TLS) or any Redis server.

REDIS_URL examples:
    Upstash : rediss://default:<password>@<name>.upstash.io:6379
    Local   : redis://localhost:6379/0
"""
from typing import Optional

import redis.asyncio as redis_async
from arq.connections import RedisSettings

from app.core.config import get_settings

settings = get_settings()

_client: Optional[redis_async.Redis] = None


def get_redis() -> redis_async.Redis:
    """Return a shared async Redis client (TLS is automatic for rediss:// URLs)."""
    global _client
    if _client is None:
        _client = redis_async.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    return _client


def get_arq_redis_settings() -> RedisSettings:
    """Redis settings for the ARQ background worker, built from the same REDIS_URL."""
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def ping_redis() -> bool:
    """True when Redis (Upstash or local) answers PING."""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False
