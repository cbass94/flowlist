"""
User repository — all database access for the users table.
Solo app: there's only ever one user, but we don't hardcode that.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_all(session: AsyncSession) -> list[User]:
    """Return all users. Solo app: usually returns exactly one."""
    result = await session.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_by_work_google_id(
    session: AsyncSession, google_id: str
) -> User | None:
    result = await session.execute(
        select(User).where(User.work_google_id == google_id)
    )
    return result.scalar_one_or_none()


async def upsert_work_account(
    session: AsyncSession,
    google_id: str,
    email: str,
    display_name: str,
    access_token: str,
    refresh_token: str,
    token_expiry: datetime,
) -> User:
    user = await get_by_work_google_id(session, google_id)
    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            work_google_id=google_id,
            work_access_token=access_token,
            work_refresh_token=refresh_token,
            work_token_expiry=token_expiry,
        )
        session.add(user)
    else:
        user.email = email
        user.display_name = display_name
        user.work_access_token = access_token
        user.work_refresh_token = refresh_token
        user.work_token_expiry = token_expiry

    await session.flush()
    return user


async def connect_personal_account(
    session: AsyncSession,
    user_id: int,
    google_id: str,
    access_token: str,
    refresh_token: str,
    token_expiry: datetime,
) -> User | None:
    user = await get_by_id(session, user_id)
    if user is None:
        return None
    user.personal_google_id = google_id
    user.personal_access_token = access_token
    user.personal_refresh_token = refresh_token
    user.personal_token_expiry = token_expiry
    await session.flush()
    return user


async def update_work_token(
    session: AsyncSession,
    user_id: int,
    access_token: str,
    token_expiry: datetime,
) -> None:
    from sqlalchemy import update
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(work_access_token=access_token, work_token_expiry=token_expiry)
    )


async def update_settings(
    session: AsyncSession,
    user_id: int,
    *,
    timezone: str | None = None,
    display_name: str | None = None,
    work_start_hour: int | None = None,
    work_end_hour: int | None = None,
    hard_start_hour: int | None = None,
    hard_end_hour: int | None = None,
    buffer_minutes: int | None = None,
    work_calendar_id: str | None = None,
    personal_calendar_id: str | None = None,
    allow_work_on_weekends: bool | None = None,
    allow_personal_on_weekends: bool | None = None,
) -> User | None:
    """Update user profile and scheduling settings. Only updates provided (non-None) fields."""
    user = await get_by_id(session, user_id)
    if user is None:
        return None
    if timezone is not None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        tz_value = timezone
        try:
            ZoneInfo(tz_value)
        except (ZoneInfoNotFoundError, KeyError):
            try:
                ZoneInfo(f"America/{tz_value}")
                tz_value = f"America/{tz_value}"
            except (ZoneInfoNotFoundError, KeyError):
                pass  # store as-is; calendar_service has its own fallback
        user.timezone = tz_value
    if display_name is not None:
        user.display_name = display_name
    if work_start_hour is not None:
        user.work_start_hour = work_start_hour
    if work_end_hour is not None:
        user.work_end_hour = work_end_hour
    if hard_start_hour is not None:
        user.hard_start_hour = hard_start_hour
    if hard_end_hour is not None:
        user.hard_end_hour = hard_end_hour
    if buffer_minutes is not None:
        user.buffer_minutes = buffer_minutes
    if work_calendar_id is not None:
        user.work_calendar_id = work_calendar_id
    if personal_calendar_id is not None:
        user.personal_calendar_id = personal_calendar_id
    if allow_work_on_weekends is not None:
        user.allow_work_on_weekends = allow_work_on_weekends
    if allow_personal_on_weekends is not None:
        user.allow_personal_on_weekends = allow_personal_on_weekends
    await session.flush()
    return user


async def update_personal_token(
    session: AsyncSession,
    user_id: int,
    access_token: str,
    token_expiry: datetime,
) -> None:
    from sqlalchemy import update
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(personal_access_token=access_token, personal_token_expiry=token_expiry)
    )
