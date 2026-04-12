"""
Shared Redis-based rate limiter.

Uses the existing shared redis_client pool — no per-call pool creation.
Fails open on Redis errors so infra issues don't block the app.
"""

import logging

from fastapi import HTTPException, Request

from app.services.redis_client import get_redis

log = logging.getLogger(__name__)


async def check_rate_limit(
    key: str,
    limit: int,
    window_secs: int,
    error_msg: str | None = None,
) -> None:
    """
    Increment a Redis counter for `key` and raise 429 if it exceeds `limit`
    within `window_secs`. Fails open on Redis errors.
    """
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_secs)
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail=error_msg
                or f"Rate limit exceeded: max {limit} requests per {window_secs}s",
            )
    except HTTPException:
        raise
    except Exception:
        log.warning("rate_limit: Redis unavailable for key %s", key)


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from request headers.

    Priority:
      1. CF-Connecting-IP  — set by Cloudflare (most reliable behind tunnel)
      2. X-Real-IP         — set by Caddy trusted_proxies
      3. X-Forwarded-For   — first entry in chain
      4. TCP connection IP — fallback for local dev
    """
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()

    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"
