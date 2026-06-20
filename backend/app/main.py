"""
FlowList — FastAPI application entry point.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.config import settings
from app.routers import ai, auth, invites, mixpanel_proxy, settings as settings_router, tasks, watchdog

log = logging.getLogger("flowlist.access")

# Paths excluded from access logging (too noisy)
_LOG_SKIP = {"/api/auth/me", "/api/healthz", "/health"}
_LOG_SKIP_PREFIXES = ("/api/mp/",)


# ── Request logging middleware ────────────────────────────────────────────────


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _LOG_SKIP or request.url.path.startswith(_LOG_SKIP_PREFIXES):
            return await call_next(request)

        start = time.perf_counter()

        # Decode session cookie to get user_id (best-effort)
        user_id: int | None = None
        try:
            from app.services.auth_service import decode_session_cookie, COOKIE_NAME
            cookie = request.cookies.get(COOKIE_NAME)
            if cookie:
                user_id = decode_session_cookie(cookie)
        except Exception:
            pass

        from app.services.rate_limit import get_client_ip
        client_ip = get_client_ip(request)

        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        log.info(
            "%s %s %d %.1fms ip=%s user=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_ip,
            user_id if user_id is not None else "-",
        )
        return response


# ── App lifespan ──────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    from app.services.redis_client import get_redis
    redis = get_redis()
    await redis.ping()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    from app.services.redis_client import close_pool
    await close_pool()


app = FastAPI(
    title="FlowList",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# ── Global exception handler — converts HTTPException to envelope format ──────

_STATUS_TO_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    502: "upstream_error",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"data": None, "error": {"message": exc.detail, "code": code}, "meta": {}},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(ai.router)
app.include_router(invites.router)
app.include_router(watchdog.router)
app.include_router(settings_router.router)
app.include_router(mixpanel_proxy.router)


# ── Health checks ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"], include_in_schema=False)
@app.get("/api/healthz", tags=["health"])
async def healthz() -> dict:
    """Health check — used by Cloudflare, Docker, and load balancers."""
    return {"status": "ok", "version": app.version}
