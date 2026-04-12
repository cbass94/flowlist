"""
Shared async Redis connection pool.

Call get_redis() to get a client backed by the shared pool.
The pool is initialised lazily on first use and is process-global —
safe in a single-worker Uvicorn setup.

For testing: override with fakeredis or a test Redis instance.
"""

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=10,
        )
    return _pool


def get_redis() -> Redis:
    """Return an async Redis client backed by the shared pool."""
    return Redis(connection_pool=_get_pool())


async def close_pool() -> None:
    """Drain and close the connection pool. Call from app lifespan shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
