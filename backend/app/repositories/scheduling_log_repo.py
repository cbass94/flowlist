"""
Scheduling run log repository.

Records the start of a run immediately (so crashes are visible), then the
scheduler service updates the row on completion via `complete_run`.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling_run_log import ScheduleTrigger, SchedulingRunLog


async def start_run(
    session: AsyncSession,
    trigger_reason: ScheduleTrigger,
    triggered_by_task_id: int | None = None,
) -> SchedulingRunLog:
    """
    Insert a new log row when a reschedule run begins.
    Returns the row so the caller can pass its ID to `complete_run`.
    """
    entry = SchedulingRunLog(
        trigger_reason=trigger_reason,
        triggered_by_task_id=triggered_by_task_id,
    )
    session.add(entry)
    await session.flush()
    return entry


async def complete_run(
    session: AsyncSession,
    run_id: int,
    tasks_affected: int,
    blocks_deleted: int,
    blocks_created: int,
    duration_ms: int,
    error: str | None = None,
) -> None:
    """Update a run row with results after the scheduler finishes (or fails)."""
    await session.execute(
        update(SchedulingRunLog)
        .where(SchedulingRunLog.id == run_id)
        .values(
            completed_at=datetime.now(tz=timezone.utc),
            tasks_affected=tasks_affected,
            blocks_deleted=blocks_deleted,
            blocks_created=blocks_created,
            duration_ms=duration_ms,
            error=error,
        )
    )


async def get_recent(
    session: AsyncSession, limit: int = 50
) -> list[SchedulingRunLog]:
    """Most recent runs, newest first. Used for a debug/admin view."""
    result = await session.execute(
        select(SchedulingRunLog)
        .order_by(SchedulingRunLog.triggered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_failed_runs(
    session: AsyncSession, limit: int = 20
) -> list[SchedulingRunLog]:
    """Runs that recorded an error — useful for alerting."""
    result = await session.execute(
        select(SchedulingRunLog)
        .where(SchedulingRunLog.error.isnot(None))
        .order_by(SchedulingRunLog.triggered_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
