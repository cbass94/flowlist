"""
Calendar block repository.

Key invariant: the app must NEVER delete or modify a Google Calendar event it
didn't create. This table is the authoritative list of FlowList-owned events.
Soft-deletion preserves history; the scheduler reads only non-deleted rows.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_block import CalendarBlock


# ── Read ─────────────────────────────────────────────────────────────────────


async def get_by_id(session: AsyncSession, block_id: int) -> CalendarBlock | None:
    result = await session.execute(
        select(CalendarBlock).where(CalendarBlock.id == block_id)
    )
    return result.scalar_one_or_none()


async def get_by_google_event_id(
    session: AsyncSession, google_event_id: str
) -> CalendarBlock | None:
    result = await session.execute(
        select(CalendarBlock).where(
            CalendarBlock.google_event_id == google_event_id
        )
    )
    return result.scalar_one_or_none()


async def get_active_blocks_for_task(
    session: AsyncSession, task_id: int
) -> list[CalendarBlock]:
    """All non-deleted calendar blocks for a specific task, ordered by start time."""
    result = await session.execute(
        select(CalendarBlock)
        .where(CalendarBlock.task_id == task_id, CalendarBlock.is_deleted.is_(False))
        .order_by(CalendarBlock.start_at)
    )
    return list(result.scalars().all())


async def get_all_blocks_for_task(
    session: AsyncSession, task_id: int
) -> list[CalendarBlock]:
    """All blocks (including deleted) — useful for audit/history views."""
    result = await session.execute(
        select(CalendarBlock)
        .where(CalendarBlock.task_id == task_id)
        .order_by(CalendarBlock.start_at)
    )
    return list(result.scalars().all())


async def get_active_future_blocks(
    session: AsyncSession,
    after: datetime | None = None,
) -> list[CalendarBlock]:
    """
    All non-deleted blocks with start_at >= `after` (default: now).
    Used by the scheduler to know what's already booked before rescheduling.
    """
    cutoff = after or datetime.now(tz=timezone.utc)
    result = await session.execute(
        select(CalendarBlock)
        .where(
            CalendarBlock.is_deleted.is_(False),
            CalendarBlock.start_at >= cutoff,
        )
        .order_by(CalendarBlock.start_at)
    )
    return list(result.scalars().all())


async def get_active_blocks_in_range(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> list[CalendarBlock]:
    """Active blocks that overlap with a given time range."""
    result = await session.execute(
        select(CalendarBlock).where(
            CalendarBlock.is_deleted.is_(False),
            CalendarBlock.start_at < end,
            CalendarBlock.end_at > start,
        )
    )
    return list(result.scalars().all())


# ── Write ─────────────────────────────────────────────────────────────────────


async def create(
    session: AsyncSession,
    task_id: int,
    google_event_id: str,
    calendar_id: str,
    account: str,
    start_at: datetime,
    end_at: datetime,
) -> CalendarBlock:
    block = CalendarBlock(
        task_id=task_id,
        google_event_id=google_event_id,
        calendar_id=calendar_id,
        account=account,
        start_at=start_at,
        end_at=end_at,
    )
    session.add(block)
    await session.flush()
    return block


async def soft_delete(session: AsyncSession, block_id: int) -> bool:
    """Mark a single block deleted. Returns True if the row existed."""
    result = await session.execute(
        update(CalendarBlock)
        .where(CalendarBlock.id == block_id, CalendarBlock.is_deleted.is_(False))
        .values(is_deleted=True, deleted_at=datetime.now(tz=timezone.utc))
        .returning(CalendarBlock.id)
    )
    return result.scalar_one_or_none() is not None


async def soft_delete_by_task(
    session: AsyncSession, task_id: int
) -> int:
    """
    Soft-delete all active blocks for a task.
    Returns the number of rows updated.
    Called before rescheduling a task (the old events will be deleted from GCal
    by the scheduler service before this is called).
    """
    result = await session.execute(
        update(CalendarBlock)
        .where(
            CalendarBlock.task_id == task_id,
            CalendarBlock.is_deleted.is_(False),
        )
        .values(is_deleted=True, deleted_at=datetime.now(tz=timezone.utc))
        .returning(CalendarBlock.id)
    )
    rows = result.scalars().all()
    return len(rows)


async def get_earliest_start_by_task_ids(
    session: AsyncSession,
    task_ids: list[int],
) -> dict[int, datetime]:
    """
    Return {task_id: earliest_future_start_at} for the given task IDs.
    Avoids N+1 queries when populating next_scheduled_start on a task list.
    """
    if not task_ids:
        return {}
    from sqlalchemy import func as sqlfunc
    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        select(CalendarBlock.task_id, sqlfunc.min(CalendarBlock.start_at))
        .where(
            CalendarBlock.task_id.in_(task_ids),
            CalendarBlock.is_deleted.is_(False),
            CalendarBlock.start_at >= now,
        )
        .group_by(CalendarBlock.task_id)
    )
    return dict(result.all())


async def soft_delete_future_blocks_for_user(
    session: AsyncSession,
    user_id: int,
    after: datetime | None = None,
) -> int:
    """
    Soft-delete all future active blocks across ALL tasks for a user.
    Called at the start of a full reschedule run.
    Returns count of deleted rows.
    """
    from sqlalchemy import and_

    cutoff = after or datetime.now(tz=timezone.utc)

    # Sub-select tasks for this user
    from app.models.task import Task

    task_ids_subq = select(Task.id).where(Task.user_id == user_id).scalar_subquery()

    result = await session.execute(
        update(CalendarBlock)
        .where(
            and_(
                CalendarBlock.task_id.in_(task_ids_subq),
                CalendarBlock.is_deleted.is_(False),
                CalendarBlock.start_at >= cutoff,
            )
        )
        .values(is_deleted=True, deleted_at=datetime.now(tz=timezone.utc))
        .returning(CalendarBlock.id)
    )
    return len(result.scalars().all())
