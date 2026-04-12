"""
AI router — natural language task parsing.

POST /api/ai/parse-task
    Accept a natural language task string, call Claude, and return a structured
    suggestion. Does NOT create anything — the client shows the suggestion to the
    user for confirmation before calling POST /api/tasks/.

Rate limiting: 30 requests per user per 60 seconds, enforced via Redis.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task import TaskStatus
from app.models.user import User
from app.repositories import ai_log_repo, task_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.task import ParseRequest, ParseResponse
from app.services import ai_service
from app.services.auth_service import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

_TERMINAL_STATUSES = [TaskStatus.done, TaskStatus.delegated]
_RATE_LIMIT = 30          # requests
_RATE_WINDOW_SECS = 60    # per window


async def _check_rate_limit(user_id: int) -> None:
    """Raise 429 if the user has exceeded the AI parse-task rate limit."""
    try:
        from arq import create_pool
        from app.routers.tasks import _parse_redis_url
        from app.config import settings as app_settings

        redis_settings = _parse_redis_url(app_settings.redis_url)
        pool = await create_pool(redis_settings)
        key = f"ratelimit:ai:parse:{user_id}"
        count = await pool.incr(key)
        if count == 1:
            await pool.expire(key, _RATE_WINDOW_SECS)
        await pool.aclose()

        if count > _RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {_RATE_LIMIT} AI requests per {_RATE_WINDOW_SECS}s",
            )
    except HTTPException:
        raise
    except Exception:
        # Redis failure → allow the request through (don't block on infra issues)
        log.warning("_check_rate_limit: Redis unavailable for user %d", user_id)


@router.post(
    "/parse-task",
    response_model=ApiResponse[ParseResponse],
    summary="Parse natural language task",
)
async def parse_task(
    body: ParseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ParseResponse]:
    """
    Parse a free-text task description into a structured suggestion using Claude.
    Returns estimated duration, type, priority, and keywords — not a saved task.
    """
    await _check_rate_limit(current_user.id)

    work_history = await ai_log_repo.get_recent_by_type(
        db, "work", limit=20, only_with_actuals=True
    )
    personal_history = await ai_log_repo.get_recent_by_type(
        db, "personal", limit=20, only_with_actuals=True
    )
    history = work_history if len(work_history) >= len(personal_history) else personal_history

    active_tasks = await task_repo.get_all_by_priority(
        db, current_user.id, exclude_statuses=_TERMINAL_STATUSES
    )
    backlog_preview = [t.title for t in active_tasks[:5]]

    result = await ai_service.parse_task_input(
        raw_text=body.raw_text,
        user_estimate=body.optional_user_estimate,
        history=history,
        backlog_preview=backlog_preview,
    )
    return ok(result)
