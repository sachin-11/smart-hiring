import logging
from collections.abc import AsyncGenerator

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool = ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


def get_redis_client() -> Redis:
    return Redis(connection_pool=_pool)


async def check_redis_connection() -> bool:
    client = get_redis_client()
    try:
        await client.ping()
        return True
    except Exception:
        logger.exception("Redis connection check failed")
        return False
    finally:
        await client.aclose()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that yields an async Redis client."""
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    await _pool.disconnect()
    logger.info("Redis connection pool disconnected.")
