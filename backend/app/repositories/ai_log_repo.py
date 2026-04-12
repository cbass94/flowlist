"""
AI estimation log repository.

Provides logging and historical lookup for the AI estimation feedback loop.
When a task is completed, `record_actual` is called to fill in the actual
duration so future prompts can include "you estimated X, actual was Y" context.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_estimation_log import AIEstimationLog


async def log_estimation(
    session: AsyncSession,
    task_id: int | None,
    task_type: str,
    task_title_snapshot: str,
    estimated_minutes: int,
    model_used: str,
    keywords: list[str] | None = None,
) -> AIEstimationLog:
    """
    Record a new AI estimation. Called immediately after AI parses a task.
    `actual_minutes` starts null and is filled in when the task completes.
    """
    entry = AIEstimationLog(
        task_id=task_id,
        task_type=task_type,
        task_title_snapshot=task_title_snapshot,
        estimated_minutes=estimated_minutes,
        model_used=model_used,
        keywords=keywords,
    )
    session.add(entry)
    await session.flush()
    return entry


async def record_actual(
    session: AsyncSession, task_id: int, actual_minutes: int
) -> AIEstimationLog | None:
    """
    Fill in actual_minutes and compute error_minutes when a task is marked done.
    Updates the most recent log entry for this task.
    """
    # Find the latest estimation entry for this task
    result = await session.execute(
        select(AIEstimationLog)
        .where(AIEstimationLog.task_id == task_id)
        .order_by(AIEstimationLog.created_at.desc())
        .limit(1)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    await session.execute(
        update(AIEstimationLog)
        .where(AIEstimationLog.id == entry.id)
        .values(
            actual_minutes=actual_minutes,
            error_minutes=actual_minutes - entry.estimated_minutes,
        )
    )
    await session.refresh(entry)
    return entry


async def get_recent_by_type(
    session: AsyncSession,
    task_type: str,
    limit: int = 20,
    only_with_actuals: bool = True,
) -> list[AIEstimationLog]:
    """
    Fetch recent estimation history for a given task type.
    Passed as context to the AI when estimating a new task.
    `only_with_actuals=True` skips entries where actual is still unknown.
    """
    stmt = (
        select(AIEstimationLog)
        .where(AIEstimationLog.task_type == task_type)
        .order_by(AIEstimationLog.created_at.desc())
        .limit(limit)
    )
    if only_with_actuals:
        stmt = stmt.where(AIEstimationLog.actual_minutes.isnot(None))

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_for_task(
    session: AsyncSession, task_id: int
) -> list[AIEstimationLog]:
    result = await session.execute(
        select(AIEstimationLog)
        .where(AIEstimationLog.task_id == task_id)
        .order_by(AIEstimationLog.created_at.desc())
    )
    return list(result.scalars().all())
