"""
Bucket-override repository — persistence for user corrections to calendar
color-coding classification.

Each row says "events matching this key belong in this bucket", keyed by
(user_id, scope, match_key). See app.models.bucket_override.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bucket_override import BucketOverride

# How many corrections to show the classifier. Enough to teach the user's
# preferences, small enough to stay a hint rather than the bulk of the prompt.
PROMPT_CORRECTION_LIMIT = 20


async def get_by_user(session: AsyncSession, user_id: int) -> list[BucketOverride]:
    result = await session.execute(
        select(BucketOverride).where(BucketOverride.user_id == user_id)
    )
    return list(result.scalars().all())


async def get_one(
    session: AsyncSession, user_id: int, scope: str, match_key: str
) -> BucketOverride | None:
    result = await session.execute(
        select(BucketOverride).where(
            BucketOverride.user_id == user_id,
            BucketOverride.scope == scope,
            BucketOverride.match_key == match_key,
        )
    )
    return result.scalar_one_or_none()


async def get_buckets_by_scope(
    session: AsyncSession, user_id: int, scope: str
) -> dict[str, str]:
    """
    Return {match_key: bucket} for one scope. Lets the task list show each task's
    pinned bucket in a single query rather than one per row.
    """
    result = await session.execute(
        select(BucketOverride.match_key, BucketOverride.bucket).where(
            BucketOverride.user_id == user_id,
            BucketOverride.scope == scope,
        )
    )
    return {match_key: bucket for match_key, bucket in result.all()}


async def upsert(
    session: AsyncSession,
    *,
    user_id: int,
    scope: str,
    match_key: str,
    bucket: str,
    was_bucket: str | None = None,
    example_summary: str | None = None,
    source: str = "app",
) -> BucketOverride:
    """Insert or update the override for (user_id, scope, match_key)."""
    row = await get_one(session, user_id, scope, match_key)
    if row is None:
        row = BucketOverride(
            user_id=user_id,
            scope=scope,
            match_key=match_key,
            bucket=bucket,
            was_bucket=was_bucket,
            example_summary=example_summary,
            source=source,
        )
        session.add(row)
    else:
        row.bucket = bucket
        # Keep the first recorded was_bucket: it's what the AI originally got
        # wrong, which is the useful half of the correction. A later edit that
        # passes None must not erase it.
        if was_bucket is not None:
            row.was_bucket = was_bucket
        if example_summary is not None:
            row.example_summary = example_summary
        row.source = source
        row.updated_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return row


async def remove(
    session: AsyncSession, user_id: int, scope: str, match_key: str
) -> bool:
    """Drop an override. Returns whether a row was actually deleted."""
    result = await session.execute(
        delete(BucketOverride).where(
            BucketOverride.user_id == user_id,
            BucketOverride.scope == scope,
            BucketOverride.match_key == match_key,
        )
    )
    return bool(result.rowcount)


async def recent_for_prompt(
    session: AsyncSession,
    user_id: int,
    limit: int = PROMPT_CORRECTION_LIMIT,
) -> list[BucketOverride]:
    """
    The most recently touched overrides that carry enough context to be worth
    showing Claude: a human-readable summary and a bucket the AI got wrong.

    Rows without those teach nothing ("something, somewhere, is purposeful"), so
    they are filtered out here rather than rendered as noise in the prompt.
    """
    result = await session.execute(
        select(BucketOverride)
        .where(
            BucketOverride.user_id == user_id,
            BucketOverride.example_summary.isnot(None),
            BucketOverride.was_bucket.isnot(None),
            BucketOverride.was_bucket != BucketOverride.bucket,
        )
        .order_by(BucketOverride.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
