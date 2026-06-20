"""
Task repository — all database access for the tasks table.

Design notes:
- Every method takes an AsyncSession; callers control transaction boundaries.
- `reorder` uses a single UPDATE...FROM VALUES query to avoid N round-trips.
- Priority integers are 1-based sequential (1 = highest). On reorder the caller
  passes a complete ordered list of IDs and we renumber from 1.
"""

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import Task, TaskStatus, TaskType


# ── Read ─────────────────────────────────────────────────────────────────────


async def get_by_id(session: AsyncSession, task_id: int) -> Task | None:
    result = await session.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def get_by_id_with_blocks(session: AsyncSession, task_id: int) -> Task | None:
    """Fetch task with its calendar_blocks eagerly loaded."""
    result = await session.execute(
        select(Task)
        .options(selectinload(Task.calendar_blocks))
        .where(Task.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_all_by_priority(
    session: AsyncSession,
    user_id: int,
    exclude_statuses: Sequence[TaskStatus] | None = None,
) -> list[Task]:
    """
    Return all tasks for a user ordered by priority ascending (1 = highest).
    Optionally exclude tasks in certain statuses (e.g., done, delegated).
    """
    stmt = select(Task).where(Task.user_id == user_id).order_by(Task.priority)
    if exclude_statuses:
        stmt = stmt.where(Task.status.notin_(exclude_statuses))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_by_status(
    session: AsyncSession, user_id: int, status: TaskStatus
) -> list[Task]:
    result = await session.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.status == status)
        .order_by(Task.priority)
    )
    return list(result.scalars().all())


async def get_watchdog_candidates(
    session: AsyncSession, user_id: int, threshold_days: int
) -> list[Task]:
    """
    Tasks that are NOT done/delegated and were created more than `threshold_days` ago
    without being completed. The watchdog worker calls this to set procrastination_flag.
    """
    cutoff = datetime.now(tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta

    cutoff = cutoff - timedelta(days=threshold_days)

    result = await session.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.status.notin_([TaskStatus.done, TaskStatus.delegated]),
            Task.updated_at <= cutoff,
        )
    )
    return list(result.scalars().all())


async def get_procrastination_flagged(
    session: AsyncSession, user_id: int
) -> list[Task]:
    """Return tasks currently flagged by the watchdog (for the dashboard widget)."""
    result = await session.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.procrastination_flag.is_(True),
        )
    )
    return list(result.scalars().all())


async def get_tentatively_done(session: AsyncSession, user_id: int) -> list[Task]:
    """Tasks awaiting the 'confirm complete or reschedule' prompt."""
    return await get_by_status(session, user_id, TaskStatus.tentatively_done)


async def get_continuation_tasks(session: AsyncSession, parent_task_id: int) -> list[Task]:
    """Return all tasks that are continuations (Part 2, etc.) of the given parent task."""
    result = await session.execute(
        select(Task).where(Task.part_of_task_id == parent_task_id)
    )
    return list(result.scalars().all())


# ── Write ─────────────────────────────────────────────────────────────────────


async def create(
    session: AsyncSession,
    user_id: int,
    title: str,
    task_type: TaskType,
    priority: int,
    *,
    estimated_duration_minutes: int | None = None,
    optional_user_estimate: str | None = None,
    optional_deadline: datetime | None = None,
    is_off_hours_allowed: bool = False,
    is_workday_allowed: bool = False,
    no_weekends: bool = False,
    part_of_task_id: int | None = None,
    description: str | None = None,
) -> Task:
    task = Task(
        user_id=user_id,
        title=title,
        type=task_type,
        priority=priority,
        status=TaskStatus.backlog,
        estimated_duration_minutes=estimated_duration_minutes,
        optional_user_estimate=optional_user_estimate,
        optional_deadline=optional_deadline,
        is_off_hours_allowed=is_off_hours_allowed,
        is_workday_allowed=is_workday_allowed,
        no_weekends=no_weekends,
        part_of_task_id=part_of_task_id,
        description=description,
    )
    session.add(task)
    await session.flush()  # populate task.id without committing
    return task


async def update_fields(
    session: AsyncSession, task_id: int, **kwargs
) -> Task | None:
    """
    Partial update — pass only the fields to change as kwargs.
    Returns the updated Task or None if not found.
    """
    stmt = (
        update(Task)
        .where(Task.id == task_id)
        .values(**kwargs)
        .returning(Task)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def reorder(
    session: AsyncSession, user_id: int, ordered_task_ids: list[int]
) -> None:
    """
    Bulk-update priorities for a user's tasks in a single SQL statement.

    `ordered_task_ids` is the complete desired order: index 0 gets priority 1,
    index 1 gets priority 2, etc. Every active task should be present.

    Uses a CASE expression to achieve a single round-trip:
        UPDATE tasks
        SET priority = CASE id WHEN 5 THEN 1 WHEN 3 THEN 2 ... END
        WHERE id IN (5, 3, ...) AND user_id = :user_id
    """
    if not ordered_task_ids:
        return

    priority_map = {task_id: idx + 1 for idx, task_id in enumerate(ordered_task_ids)}

    case_expr = case(priority_map, value=Task.id)

    await session.execute(
        update(Task)
        .where(Task.id.in_(ordered_task_ids), Task.user_id == user_id)
        .values(priority=case_expr)
    )


async def mark_complete(
    session: AsyncSession, task_id: int, actual_duration_minutes: int | None = None
) -> Task | None:
    return await update_fields(
        session,
        task_id,
        status=TaskStatus.done,
        actual_duration_minutes=actual_duration_minutes,
        completed_at=datetime.now(tz=timezone.utc),
        procrastination_flag=False,
    )


async def set_procrastination_flag(
    session: AsyncSession, task_id: int, flagged: bool
) -> None:
    await update_fields(session, task_id, procrastination_flag=flagged)


async def delete(session: AsyncSession, task_id: int) -> bool:
    """Hard delete. Returns True if a row was deleted."""
    task = await get_by_id(session, task_id)
    if task is None:
        return False
    await session.delete(task)
    return True


async def get_next_priority(session: AsyncSession, user_id: int) -> int:
    """Return the next available priority integer (max + 1, or 1 if no tasks)."""
    from sqlalchemy import func

    result = await session.execute(
        select(func.max(Task.priority)).where(Task.user_id == user_id)
    )
    max_priority = result.scalar_one_or_none()
    return (max_priority or 0) + 1


async def insert_at_top(session: AsyncSession, user_id: int) -> None:
    """
    Shift all active (non-terminal) tasks' priorities up by 1 to make room
    for a new task at priority 1.
    """
    await session.execute(
        update(Task)
        .where(
            Task.user_id == user_id,
            Task.status.notin_([TaskStatus.done, TaskStatus.delegated]),
        )
        .values(priority=Task.priority + 1)
    )


async def get_archive(
    session: AsyncSession,
    user_id: int,
    task_type: "TaskType | None" = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    """Return done + delegated tasks, most recently completed first."""
    stmt = (
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status.in_([TaskStatus.done, TaskStatus.delegated]),
        )
        .order_by(Task.completed_at.desc().nulls_last(), Task.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if task_type is not None:
        stmt = stmt.where(Task.type == task_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())
