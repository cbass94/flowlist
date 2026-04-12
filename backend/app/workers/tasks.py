"""
ARQ background worker — all async jobs and cron tasks for FlowList.

Jobs:
  reschedule_all(ctx, user_id, token)
      Full or windowed reschedule triggered by API endpoints.
      Uses a debounce token so rapid bursts (e.g. drag-to-reorder) only
      fire one reschedule: the last writer wins.

Cron tasks:
  tentatively_done_checker(ctx)
      Runs every 15 minutes. Transitions tasks whose scheduled block end-times
      have passed (and the task isn't marked done) to "tentatively_done".

  procrastination_watchdog(ctx)
      Runs daily at 8am. Sets procrastination_flag on tasks that have been
      sitting unfinished for 14+ days.

  weekly_full_reschedule(ctx)
      Runs weekly on Sunday at 20:00 (8pm). Full reschedule for all users.

Worker startup:
  The ARQ worker is started by docker-compose as a separate container running:
      arq app.workers.tasks.WorkerSettings
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.task import TaskStatus
from app.repositories import calendar_block_repo, task_repo, user_repo
from app.services import scheduler_service

log = logging.getLogger(__name__)

# Redis key for debounce tokens: "reschedule:token:{user_id}"
_DEBOUNCE_KEY = "reschedule:token:{user_id}"


# ── Startup / shutdown hooks ──────────────────────────────────────────────────


async def startup(ctx: dict) -> None:
    """Called once when the worker process starts."""
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


async def tentatively_done_checker(ctx: dict) -> None:
    """
    Check every 15 minutes for scheduled tasks whose calendar block end-time
    has passed without the task being marked done. Transition those to
    "tentatively_done" so the user gets a review prompt.
    """
    now = datetime.now(tz=timezone.utc)
    log.debug("tentatively_done_checker: running at %s", now.isoformat())

    async with AsyncSessionLocal() as db:
        users = await user_repo.get_all(db)
        for user in users:
            await _check_tentatively_done_for_user(db, user.id, now)


async def _check_tentatively_done_for_user(
    db: AsyncSession,
    user_id: int,
    now: datetime,
) -> None:
    """
    For a single user, find scheduled tasks whose latest block has ended
    and transition them to tentatively_done.
    """
    scheduled_tasks = await task_repo.get_by_status(db, user_id, TaskStatus.scheduled)

    for task in scheduled_tasks:
        # Get all active (non-deleted) blocks for this task
        blocks = await calendar_block_repo.get_active_blocks_for_task(db, task.id)
        if not blocks:
            continue

        # The task's latest block — if it has ended, prompt the user
        latest_block = max(blocks, key=lambda b: b.end_at)
        if latest_block.end_at <= now:
            await task_repo.update_fields(
                db, task.id, status=TaskStatus.tentatively_done
            )
            await db.commit()
            log.info(
                "tentatively_done_checker: task %d '%s' → tentatively_done",
                task.id, task.title[:40],
            )


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

    # Clear flag on tasks that have since been completed or are recently active
    flagged = await task_repo.get_procrastination_flagged(db, user_id)
    terminal = {TaskStatus.done, TaskStatus.delegated}
    for task in flagged:
        if task.status in terminal:
            await task_repo.set_procrastination_flag(db, task.id, False)
            await db.commit()
            cleared_count += 1

    if flagged_count or cleared_count:
        log.info(
            "procrastination_watchdog: user %d flagged=%d cleared=%d",
            user_id, flagged_count, cleared_count,
        )


async def weekly_full_reschedule(ctx: dict) -> None:
    """
    Weekly full reschedule (Sunday 20:00). Re-optimises the entire future backlog
    against the real calendar, consolidating any gaps that have built up.
    """
    log.info("weekly_full_reschedule: starting")
    async with AsyncSessionLocal() as db:
        users = await user_repo.get_all(db)
        for user in users:
            await scheduler_service.schedule_all_tasks(
                db=db,
                user=user,
                trigger=ScheduleTrigger.startup,  # closest semantic match
            )
    log.info("weekly_full_reschedule: done")


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
        # Tentatively-done checker: every 15 minutes
        cron(tentatively_done_checker, minute={0, 15, 30, 45}),
        # Procrastination watchdog: daily at 8:00am
        cron(procrastination_watchdog, hour=8, minute=0),
        # Weekly full reschedule: Sunday at 20:00
        cron(weekly_full_reschedule, weekday=6, hour=20, minute=0),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = _parse_redis_url(settings.redis_url)

    # Retry failed jobs up to 2 times with exponential backoff
    max_tries = 3
    job_timeout = 300  # 5 minutes max per job

    # Logging
    log_results = True
