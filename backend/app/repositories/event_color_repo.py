"""
Event-color repository — persistence for AI calendar color-coding.

Each row records FlowList's classification + applied color for one calendar
event, keyed by (user_id, google_event_id). See app.models.event_color.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_color import EventColor


async def get_by_user(session: AsyncSession, user_id: int) -> list[EventColor]:
    result = await session.execute(
        select(EventColor).where(EventColor.user_id == user_id)
    )
    return list(result.scalars().all())


async def upsert(
    session: AsyncSession,
    *,
    user_id: int,
    calendar_id: str,
    google_event_id: str,
    bucket: str,
    applied_color_id: str,
    content_signature: str,
    is_user_overridden: bool = False,
) -> EventColor:
    """Insert or update the record for (user_id, google_event_id)."""
    existing = await session.execute(
        select(EventColor).where(
            EventColor.user_id == user_id,
            EventColor.google_event_id == google_event_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = EventColor(
            user_id=user_id,
            calendar_id=calendar_id,
            google_event_id=google_event_id,
            bucket=bucket,
            applied_color_id=applied_color_id,
            content_signature=content_signature,
            is_user_overridden=is_user_overridden,
        )
        session.add(row)
    else:
        row.calendar_id = calendar_id
        row.bucket = bucket
        row.applied_color_id = applied_color_id
        row.content_signature = content_signature
        row.is_user_overridden = is_user_overridden
        row.updated_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return row


async def mark_overridden(session: AsyncSession, row: EventColor) -> None:
    """Cede control of an event whose color the user changed by hand."""
    row.is_user_overridden = True
    row.updated_at = datetime.now(tz=timezone.utc)
    await session.flush()


async def prune(
    session: AsyncSession,
    user_id: int,
    keep_event_ids: set[str],
) -> int:
    """
    Delete records for a user whose events are no longer in the working window
    (event cancelled / moved out / deleted). Returns rows removed.
    """
    rows = await get_by_user(session, user_id)
    stale_ids = [r.google_event_id for r in rows if r.google_event_id not in keep_event_ids]
    if not stale_ids:
        return 0
    await session.execute(
        delete(EventColor).where(
            EventColor.user_id == user_id,
            EventColor.google_event_id.in_(stale_ids),
        )
    )
    return len(stale_ids)
