"""
ARQ background worker — all async jobs and cron tasks for FlowList.

Jobs:
  reschedule_all(ctx, user_id, token)
      Full or windowed reschedule triggered by API endpoints.
      Uses a debounce token so rapid bursts (e.g. drag-to-reorder) only
      fire one reschedule: the last writer wins.

Cron tasks:
  procrastination_watchdog(ctx)
      Runs daily at 8am. Sets procrastination_flag on tasks that have been
      sitting unfinished for 14+ days.

  daily_full_reschedule(ctx)
      Runs daily at 09:00 UTC (~4am America/Chicago). Full reschedule for all
      users — re-optimises the entire future backlog against the real calendar,
      catching anything left behind by 72h windowed (priority-change) runs.

Worker startup:
  The ARQ worker is started by docker-compose as a separate container running:
      arq app.workers.tasks.WorkerSettings
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.task import TaskStatus
from app.repositories import task_repo, user_repo
from app.services import scheduler_service

log = logging.getLogger(__name__)

# Redis key for debounce tokens: "reschedule:token:{user_id}"
_DEBOUNCE_KEY = "reschedule:token:{user_id}"


# ── Startup / shutdown hooks ──────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Called once when the worker process starts."""
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    log.info("FlowList worker starting up")
    # Use the regex-based parser instead of aioredis.from_url(), which uses
    # Python's urlparse and breaks when the password contains '#' (treated
    # as a URL fragment delimiter, dropping the hostname).
    rs = _parse_redis_url(settings.redis_url)
    ctx["redis"] = aioredis.Redis(
        host=rs.host,
        port=rs.port,
        password=rs.password,
        db=rs.database,
        decode_responses=True,
    )


async def shutdown(ctx: dict) -> None:
    """Called once when the worker process shuts down."""
    log.info("FlowList worker shutting down")
    if "redis" in ctx:
        await ctx["redis"].aclose()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_redis_url(url: str) -> RedisSettings:
    """
    Convert a redis:// or rediss:// URL string into an ARQ RedisSettings object.

    Uses regex instead of urllib.parse.urlparse because urlparse treats '#' as a
    URL fragment delimiter, which silently drops the hostname when the Redis
    password contains a '#' character (e.g. redis://:pa#ss@redis:6379/0 would
    parse with hostname=None and fall back to localhost).

    Pattern handles: redis://:password@host:port/db
    The password group [^@]* matches any character except '@', including '#'.
    """
    import re
    from urllib.parse import unquote
    # Strip scheme prefix
    rest = re.sub(r"^rediss?://", "", url.strip())
    m = re.match(
        r"^(?::(?P<password>[^@]*)@)?"   # optional :password@
        r"(?P<host>[^:/]+)"              # hostname
        r"(?::(?P<port>\d+))?"           # optional :port
        r"(?:/(?P<db>\d+))?",            # optional /db
        rest,
    )
    if not m:
        return RedisSettings()
    raw_password = m.group("password")
    return RedisSettings(
        host=m.group("host") or "localhost",
        port=int(m.group("port") or 6379),
        password=unquote(raw_password) if raw_password else None,
        database=int(m.group("db") or 0),
    )


# ── Jobs ─────────────────────────────────────────────────────────────────────


async def reschedule_all(ctx: dict, user_id: int, token: str) -> None:
    """
    ARQ job: run a full (or windowed) reschedule for a user.

    Debounce: each call passes a `token` string. Before running, the job reads
    the current token stored in Redis under "reschedule:token:{user_id}". If
    the stored token differs from the passed token, a newer reschedule has been
    enqueued and this job silently exits.

    This means only the LAST enqueued job (the one that stored its token last)
    actually runs, discarding all intermediate ones.

    The trigger is stored as part of the token so we know the reason.
    """
    redis: aioredis.Redis = ctx["redis"]
    key = _DEBOUNCE_KEY.format(user_id=user_id)
    current_token = await redis.get(key)

    if current_token is not None and current_token != token:
        log.info(
            "reschedule_all: debounced for user %d (token %s superseded by %s)",
            user_id, token[:8], current_token[:8],
        )
        return

    # Determine trigger from token prefix (format: "{trigger}:{uuid}")
    trigger_str = token.split(":")[0] if ":" in token else "manual"
    try:
        trigger = ScheduleTrigger(trigger_str)
    except ValueError:
        trigger = ScheduleTrigger.manual

    async with AsyncSessionLocal() as db:
        user = await user_repo.get_by_id(db, user_id)
        if user is None:
            log.warning("reschedule_all: user %d not found", user_id)
            return

        await scheduler_service.schedule_all_tasks(
            db=db,
            user=user,
            trigger=trigger,
        )


# ── Cron tasks ────────────────────────────────────────────────────────────────


async def procrastination_watchdog(ctx: dict) -> None:
    """
    Daily watchdog: set procrastination_flag on tasks that have been sitting
    unfinished/unscheduled for 14+ days. Also clears the flag on tasks that
    no longer qualify (completed or recently updated).
    """
    threshold = settings.watchdog_threshold_days
    log.info("procrastination_watchdog: running (threshold=%d days)", threshold)

    async with AsyncSessionLocal() as db:
        users = await user_repo.get_all(db)
        for user in users:
            await _run_watchdog_for_user(db, user.id, threshold)


async def _run_watchdog_for_user(
    db: AsyncSession,
    user_id: int,
    threshold_days: int,
) -> None:
    flagged_count = 0
    cleared_count = 0

    # Find candidates for flagging (not done/delegated, created long ago)
    candidates = await task_repo.get_watchdog_candidates(db, user_id, threshold_days)
    for task in candidates:
        if not task.procrastination_flag:
            await task_repo.set_procrastination_flag(db, task.id, True)
            await db.commit()
            flagged_count += 1

    # Clear flag on tasks that are now terminal or have been touched recently
    from datetime import timedelta
    cutoff = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=threshold_days)
    flagged = await task_repo.get_procrastination_flagged(db, user_id)
    terminal = {TaskStatus.done, TaskStatus.delegated}
    for task in flagged:
        if task.status in terminal or task.updated_at > cutoff:
            await task_repo.set_procrastination_flag(db, task.id, False)
            await db.commit()
            cleared_count += 1

    if flagged_count or cleared_count:
        log.info(
            "procrastination_watchdog: user %d flagged=%d cleared=%d",
            user_id, flagged_count, cleared_count,
        )


async def daily_full_reschedule(ctx: dict) -> None:
    """
    Daily full reschedule (09:00 UTC ≈ 4am America/Chicago). Re-optimises the
    entire future backlog against the real calendar, consolidating gaps and
    re-sorting everything into strict priority order. Runs overnight so it never
    shifts blocks around while the user is mid-day.

    This catches up anything that 72h windowed (priority-change) reschedules
    left behind beyond their window.
    """
    log.info("daily_full_reschedule: starting")
    async with AsyncSessionLocal() as db:
        users = await user_repo.get_all(db)
        for user in users:
            await scheduler_service.schedule_all_tasks(
                db=db,
                user=user,
                trigger=ScheduleTrigger.startup,  # closest semantic match
            )
    log.info("daily_full_reschedule: done")


# ── Worker settings ───────────────────────────────────────────────────────────


class WorkerSettings:
    """
    ARQ worker configuration.

    ARQ reads this class to discover jobs, cron tasks, and Redis connection info.
    Start the worker with:
        arq app.workers.tasks.WorkerSettings
    """

    functions = [reschedule_all]

    cron_jobs = [
        # Procrastination watchdog: daily at 8:00am UTC
        cron(procrastination_watchdog, hour=8, minute=0),
        # Full reschedule: daily at 09:00 UTC (~4am America/Chicago) — overnight
        # so it never shifts upcoming blocks while the user is mid-day.
        cron(daily_full_reschedule, hour=9, minute=0),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = _parse_redis_url(settings.redis_url)

    # Retry failed jobs up to 2 times with exponential backoff
    max_tries = 3
    job_timeout = 300  # 5 minutes max per job

    # Logging
    log_results = True
