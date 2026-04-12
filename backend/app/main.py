"""
FlowList — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import ai, auth, review_prompts, settings as settings_router, tasks, watchdog


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    # Warm the Redis connection pool
    from app.services.redis_client import get_redis
    redis = get_redis()
    await redis.ping()

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    from app.services.redis_client import close_pool
    await close_pool()


app = FastAPI(
    title="FlowList",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler — converts HTTPException to envelope format ──────

_STATUS_TO_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
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
app.include_router(review_prompts.router)
app.include_router(watchdog.router)
app.include_router(settings_router.router)


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/healthz", tags=["health"])
async def healthz() -> dict:
    return {"status": "ok", "version": app.version}
