"""
Google Calendar service.

All Google API calls are synchronous (the google-api-python-client library
does not support asyncio). Each call is run via asyncio.to_thread() so it
does not block the event loop.

Key invariants enforced here:
  - The app ONLY deletes/modifies events whose google_event_id exists in the
    calendar_blocks table (i.e. events FlowList created).
  - All created events are stamped with a [FlowList] description prefix and
    an extendedProperties.private tag so they can be reliably identified.
  - Token refresh is automatic: if an access token is expired, we refresh and
    persist the new token before making the Google API call.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

from app.config import settings
from app.models.calendar_block import CalendarBlock
from app.models.task import Task, TaskType
from app.models.user import User
from app.repositories import calendar_block_repo, user_repo
from app.services import crypto
from app.services import oauth as oauth_service
from app.services.slot_finder import (
    SlotFinderConfig,
    find_free_slots,
    merge_intervals,
)

# Tag embedded in every FlowList-created event
FLOWLIST_TAG = "[FlowList]"

AccountType = Literal["work", "personal"]


# ── Credential management ─────────────────────────────────────────────────────


async def _get_valid_credentials(
    user: User,
    account: AccountType,
    db: AsyncSession,
) -> Credentials:
    """
    Return a valid Google Credentials object for the given account, refreshing
    the access token if it has expired or is within 5 minutes of expiry.
    Persists refreshed tokens back to the DB.
    """
    if account == "work":
        raw_access = user.work_access_token
        raw_refresh = user.work_refresh_token
        expiry = user.work_token_expiry
        client_id = settings.google_work_client_id
        client_secret = settings.google_work_client_secret
    else:
        if not user.personal_google_id:
            raise ValueError("Personal Google account is not connected")
        raw_access = user.personal_access_token
        raw_refresh = user.personal_refresh_token
        expiry = user.personal_token_expiry
        client_id = settings.google_personal_client_id
        client_secret = settings.google_personal_client_secret

    if not raw_access or not raw_refresh:
        raise ValueError(f"{account} account tokens are missing — user must re-authenticate")

    access_token = crypto.decrypt(raw_access)
    refresh_token = crypto.decrypt(raw_refresh)

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
    )
    if expiry:
        creds.expiry = expiry.replace(tzinfo=None)  # google-auth expects naive UTC

    # Refresh if expired or expiring within 5 minutes
    needs_refresh = (
        creds.expired
        or expiry is None
        or expiry <= datetime.now(tz=timezone.utc) + timedelta(minutes=5)
    )
    if needs_refresh:
        log.info("_get_valid_credentials: refreshing %s token for user %d", account, user.id)
        try:
            new_access, new_expiry = await oauth_service.refresh_access_token(
                account, refresh_token
            )
        except ValueError as exc:
            if account == "personal" and "invalid_grant" in str(exc):
                log.warning(
                    "_get_valid_credentials: personal token revoked for user %d — auto-disconnecting",
                    user.id,
                )
                async with db.begin_nested():
                    await user_repo.disconnect_personal_account(db, user.id)
                raise ValueError(
                    "Personal Google account authorization has expired. "
                    "Please reconnect your personal account in Settings."
                ) from exc
            raise
        creds = Credentials(
            token=new_access,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        # Persist new token
        async with db.begin_nested():
            if account == "work":
                await user_repo.update_work_token(db, user.id, crypto.encrypt(new_access), new_expiry)
            else:
                await user_repo.update_personal_token(db, user.id, crypto.encrypt(new_access), new_expiry)
        log.info("_get_valid_credentials: refreshed and persisted %s token for user %d", account, user.id)

    return creds


def _build_service(credentials: Credentials):
    """Build a Google Calendar API service. Synchronous — call via asyncio.to_thread."""
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


# ── Event helpers ─────────────────────────────────────────────────────────────


def _build_gcal_description(task: Task) -> str:
    """
    Build the Google Calendar event description string for a FlowList task.

    Format when task has a description:
        [user description text]

        ---
        [FlowList] task_id: {id}

    Format when no description:
        [FlowList] task_id: {id}
    """
    footer = f"{FLOWLIST_TAG} task_id: {task.id}"
    if task.description:
        return f"{task.description}\n\n---\n{footer}"
    return footer


def _build_event_body(task: Task, start_dt: datetime, end_dt: datetime) -> dict[str, Any]:
    """Build the Google Calendar event resource dict for a FlowList task block."""
    return {
        "summary": task.title,
        "description": _build_gcal_description(task),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
        # Machine-readable identifier so we can find our events robustly
        "extendedProperties": {
            "private": {
                "flowlist": "true",
                "task_id": str(task.id),
            }
        },
        "source": {
            "title": "FlowList",
            "url": settings.app_base_url,
        },
    }


def _parse_event(event: dict) -> dict[str, Any]:
    """Normalize a Google Calendar event dict to a consistent shape."""
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})
    start_str = start_raw.get("dateTime") or start_raw.get("date", "")
    end_str = end_raw.get("dateTime") or end_raw.get("date", "")

    return {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "start": start_str,
        "end": end_str,
        "is_flowlist": event.get("extendedProperties", {})
            .get("private", {})
            .get("flowlist") == "true"
            or FLOWLIST_TAG in event.get("description", ""),
        "task_id": event.get("extendedProperties", {})
            .get("private", {})
            .get("task_id"),
    }


def _parse_event_datetime(node: dict) -> datetime | None:
    """Parse a Google event start/end node into a UTC-aware datetime.

    Returns None for all-day events (which use `date`, not `dateTime`).
    """
    raw = node.get("dateTime")
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_synthesis_event(event: dict) -> dict[str, Any]:
    """
    Normalize a Google Calendar event into the shape the synthesis logic needs
    (see app.services.synthesis). Includes attendees, timing, and whether the
    event is one FlowList created.
    """
    start_raw = event.get("start", {})
    end_raw = event.get("end", {})
    is_all_day = "date" in start_raw and "dateTime" not in start_raw

    attendees = [
        {
            "email": att.get("email", ""),
            "self": bool(att.get("self", False)),
            "responseStatus": att.get("responseStatus"),
            "resource": bool(att.get("resource", False)),
        }
        for att in event.get("attendees", [])
    ]

    is_flowlist = (
        event.get("extendedProperties", {}).get("private", {}).get("flowlist") == "true"
        or FLOWLIST_TAG in event.get("description", "")
    )

    return {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
        "start_dt": _parse_event_datetime(start_raw),
        "end_dt": _parse_event_datetime(end_raw),
        "is_all_day": is_all_day,
        "status": event.get("status"),
        "event_type": event.get("eventType"),
        "attendees": attendees,
        "is_flowlist": is_flowlist,
        "transparency": event.get("transparency"),
    }


# ── Public API ────────────────────────────────────────────────────────────────


async def get_events_with_attendees(
    user: User,
    db: AsyncSession,
    calendar_id: str,
    account: AccountType,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, Any]]:
    """
    Fetch events from a calendar in [start_dt, end_dt], normalized for the
    synthesis logic (attendees, timing, FlowList ownership).

    Uses events().list (not freebusy) because we need attendee data to decide
    whether a meeting includes anyone other than the user.
    """
    creds = await _get_valid_credentials(user, account, db)

    def _fetch() -> list[dict]:
        service = _build_service(creds)
        events: list[dict] = []
        page_token = None
        while True:
            result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start_dt.isoformat(),
                    timeMax=end_dt.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return events

    raw_events = await asyncio.to_thread(_fetch)
    return [_parse_synthesis_event(e) for e in raw_events]


async def create_synthesis_block(
    user: User,
    db: AsyncSession,
    calendar_id: str,
    account: AccountType,
    start_time: datetime,
    end_time: datetime,
    source_google_event_id: str,
) -> CalendarBlock:
    """
    Create a "Synthesis time" Google Calendar event immediately after a meeting
    and record it in calendar_blocks as a synthesis block.

    Tagged like every FlowList event ([FlowList] + extendedProperties) so the
    ownership guard protects it, plus a `synthesis` marker and the source
    meeting's event ID for idempotent reconciliation.
    """
    creds = await _get_valid_credentials(user, account, db)
    event_body = {
        "summary": "Synthesis time",
        "description": (
            "Time to synthesize what came out of your last meeting before "
            "moving on.\n\n---\n" + f"{FLOWLIST_TAG} synthesis"
        ),
        "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        "extendedProperties": {
            "private": {
                "flowlist": "true",
                "synthesis": "true",
                "source_event_id": source_google_event_id,
            }
        },
        "source": {
            "title": "FlowList",
            "url": settings.app_base_url,
        },
    }

    def _insert() -> str:
        service = _build_service(creds)
        created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return created["id"]

    google_event_id = await asyncio.to_thread(_insert)

    block = await calendar_block_repo.create(
        db,
        task_id=None,
        user_id=user.id,
        block_type="synthesis",
        source_google_event_id=source_google_event_id,
        google_event_id=google_event_id,
        calendar_id=calendar_id,
        account=account,
        start_at=start_time,
        end_at=end_time,
    )
    return block


async def get_calendar_events(
    user: User,
    db: AsyncSession,
    calendar_id: str,
    account: AccountType,
    start_dt: datetime,
    end_dt: datetime,
) -> list[dict[str, Any]]:
    """
    Fetch all events from a Google Calendar in the given datetime range.
    Returns a list of normalized event dicts (see _parse_event).
    """
    creds = await _get_valid_credentials(user, account, db)

    def _fetch() -> list[dict]:
        service = _build_service(creds)
        events = []
        page_token = None
        while True:
            result = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start_dt.isoformat(),
                    timeMax=end_dt.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return events

    raw_events = await asyncio.to_thread(_fetch)
    return [_parse_event(e) for e in raw_events]


async def create_calendar_block(
    user: User,
    db: AsyncSession,
    task: Task,
    calendar_id: str,
    account: AccountType,
    start_time: datetime,
    end_time: datetime,
) -> CalendarBlock:
    """
    Create a Google Calendar event for a task block and record it in the DB.

    The event is stamped with [FlowList] in the description and a private
    extendedProperty so we can always identify it as ours.

    Returns the CalendarBlock ORM row (not yet committed — caller controls txn).
    """
    creds = await _get_valid_credentials(user, account, db)
    event_body = _build_event_body(task, start_time, end_time)

    def _insert() -> str:
        service = _build_service(creds)
        created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        return created["id"]

    google_event_id = await asyncio.to_thread(_insert)

    # Record in DB
    block = await calendar_block_repo.create(
        db,
        task_id=task.id,
        user_id=user.id,
        block_type="task",
        google_event_id=google_event_id,
        calendar_id=calendar_id,
        account=account,
        start_at=start_time,
        end_at=end_time,
    )
    return block


async def delete_calendar_block(
    user: User,
    db: AsyncSession,
    calendar_id: str,
    account: AccountType,
    google_event_id: str,
) -> None:
    """
    Delete a FlowList-owned calendar event from Google Calendar and
    soft-delete the corresponding calendar_blocks row.

    Silently ignores 404 (event already deleted from Google Calendar).
    Raises ValueError if the event_id is not in our calendar_blocks table —
    we never delete events we didn't create.
    """
    block = await calendar_block_repo.get_by_google_event_id(db, google_event_id)
    if block is None or block.is_deleted:
        # Nothing to do — either already deleted or not ours
        return

    creds = await _get_valid_credentials(user, account, db)

    def _delete() -> None:
        service = _build_service(creds)
        try:
            service.events().delete(calendarId=calendar_id, eventId=google_event_id).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                log.info(
                    "delete_calendar_block: event %s already gone from GCal (404) — soft-deleting DB record",
                    google_event_id,
                )
                return  # Already gone from Google — still soft-delete our record
            log.warning(
                "delete_calendar_block: GCal API error deleting event %s on calendar %s: status=%s reason=%s",
                google_event_id, calendar_id, exc.resp.status, exc.error_details,
            )
            raise

    await asyncio.to_thread(_delete)
    log.info(
        "delete_calendar_block: deleted event %s from GCal calendar %s (account=%s)",
        google_event_id, calendar_id, account,
    )
    await calendar_block_repo.soft_delete(db, block.id)


async def update_future_block_descriptions(
    user: User,
    db: AsyncSession,
    task: Task,
) -> None:
    """
    Patch the description of all future (not-yet-started) FlowList calendar events
    for a task. Called when a task's description field is updated.
    Past blocks are left untouched.
    """
    now = datetime.now(tz=timezone.utc)
    future_blocks = await calendar_block_repo.get_active_future_blocks_for_task(
        db, task.id, after=now
    )
    if not future_blocks:
        return

    new_description = _build_gcal_description(task)

    for block in future_blocks:
        creds = await _get_valid_credentials(user, block.account, db)  # type: ignore[arg-type]
        cal_id = block.calendar_id
        ev_id = block.google_event_id

        def _patch(_cal=cal_id, _ev=ev_id, _creds=creds) -> None:
            service = _build_service(_creds)
            service.events().patch(
                calendarId=_cal,
                eventId=_ev,
                body={"description": new_description},
            ).execute()

        try:
            await asyncio.to_thread(_patch)
            log.info(
                "update_future_block_descriptions: patched event %s for task %d",
                ev_id, task.id,
            )
        except Exception as exc:
            log.warning(
                "update_future_block_descriptions: failed to patch event %s for task %d: %s",
                ev_id, task.id, exc,
            )


async def _get_freebusy(
    user: User,
    db: AsyncSession,
    calendar_ids: list[str],
    account: AccountType,
    start_dt: datetime,
    end_dt: datetime,
) -> list[tuple[datetime, datetime]]:
    """
    Call Google's freebusy API and return merged busy intervals for the given calendars.
    All returned datetimes are UTC-aware.
    """
    creds = await _get_valid_credentials(user, account, db)

    def _query() -> dict:
        service = _build_service(creds)
        return (
            service.freebusy()
            .query(
                body={
                    "timeMin": start_dt.isoformat(),
                    "timeMax": end_dt.isoformat(),
                    "items": [{"id": cal_id} for cal_id in calendar_ids],
                }
            )
            .execute()
        )

    result = await asyncio.to_thread(_query)
    calendars_data = result.get("calendars", {})

    intervals: list[tuple[datetime, datetime]] = []
    for cal_id in calendar_ids:
        for period in calendars_data.get(cal_id, {}).get("busy", []):
            start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
            intervals.append((start, end))

    return intervals


async def find_free_slots_for_task(
    user: User,
    db: AsyncSession,
    task: Task,
    target_date: date,
    duration_minutes: int,
    min_start: datetime | None = None,
) -> list[tuple[datetime, datetime]]:
    """
    Find available slots on `target_date` for a task of `duration_minutes`.

    Checks BOTH calendars simultaneously — a slot must be free on both work
    AND personal calendars to be considered available.

    Work account has read access to both calendars (per CLAUDE.md), so a single
    freebusy call covers both. If the personal account is separately connected,
    we also query it directly and merge the results.

    Returns a list of (start, end) UTC-aware datetimes in chronological order.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    raw_tz = user.timezone or "UTC"
    try:
        user_tz = ZoneInfo(raw_tz)
    except (ZoneInfoNotFoundError, KeyError):
        # Try common short names like "Denver" → "America/Denver"
        try:
            user_tz = ZoneInfo(f"America/{raw_tz}")
        except (ZoneInfoNotFoundError, KeyError):
            import logging as _log
            _log.getLogger(__name__).warning(
                "find_free_slots_for_task: unknown timezone %r for user %d, falling back to UTC",
                raw_tz, user.id,
            )
            user_tz = ZoneInfo("UTC")

    # Build datetime range for the target date (full day in user tz, with buffer padding)
    day_start = datetime(
        target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=user_tz
    )
    day_end = day_start + timedelta(days=1)

    # Always query work account for both calendars (work account has read access to personal)
    busy_intervals = await _get_freebusy(
        user, db,
        calendar_ids=[(user.work_calendar_id or settings.work_calendar_id), (user.personal_calendar_id or settings.personal_calendar_id)],
        account="work",
        start_dt=day_start,
        end_dt=day_end,
    )

    # If personal account is separately connected, query it too for completeness
    # (handles edge case where personal account has events work account can't see)
    if user.personal_account_connected:
        personal_busy = await _get_freebusy(
            user, db,
            calendar_ids=[(user.personal_calendar_id or settings.personal_calendar_id)],
            account="personal",
            start_dt=day_start,
            end_dt=day_end,
        )
        busy_intervals.extend(personal_busy)

    # Merge all overlapping intervals from both calendars
    merged_busy = merge_intervals(busy_intervals)

    config = SlotFinderConfig(
        work_start_hour=user.work_start_hour,
        work_end_hour=user.work_end_hour,
        hard_start_hour=user.hard_start_hour,
        hard_end_hour=user.hard_end_hour,
        buffer_minutes=user.buffer_minutes,
        max_block_minutes=settings.schedule_max_block_minutes,
        min_block_minutes=settings.schedule_min_block_minutes,
        allow_work_on_weekends=user.allow_work_on_weekends,
        allow_personal_on_weekends=user.allow_personal_on_weekends,
        work_saturday_start_time=user.work_saturday_start_time,
        work_saturday_end_time=user.work_saturday_end_time,
        work_sunday_start_time=user.work_sunday_start_time,
        work_sunday_end_time=user.work_sunday_end_time,
        personal_saturday_start_time=user.personal_saturday_start_time,
        personal_saturday_end_time=user.personal_saturday_end_time,
        personal_sunday_start_time=user.personal_sunday_start_time,
        personal_sunday_end_time=user.personal_sunday_end_time,
    )

    task_type = task.type.value  # "work" or "personal"

    return find_free_slots(
        busy_intervals=merged_busy,
        target_date=target_date,
        duration_minutes=duration_minutes,
        task_type=task_type,
        user_tz=user_tz,
        config=config,
        is_off_hours_allowed=task.is_off_hours_allowed,
        is_workday_allowed=task.is_workday_allowed,
        no_weekends=task.no_weekends,
        min_start=min_start,
    )


async def get_event_by_id(
    user: User,
    db: AsyncSession,
    event_id: str,
) -> dict[str, Any] | None:
    """
    Fetch a single Google Calendar event by ID.

    Tries the work account's work and personal calendars. Returns a normalized
    event dict (same shape as _parse_event), or None if not found.
    """
    work_cal_id = user.work_calendar_id or settings.work_calendar_id
    personal_cal_id = user.personal_calendar_id or settings.personal_calendar_id
    calendar_ids_to_try = list(dict.fromkeys([work_cal_id, personal_cal_id]))

    creds = await _get_valid_credentials(user, "work", db)

    def _fetch(cal_id: str) -> dict | None:
        service = _build_service(creds)
        try:
            event = service.events().get(calendarId=cal_id, eventId=event_id).execute()
            return event
        except HttpError as exc:
            if exc.resp.status in (404, 410):
                return None
            raise

    for cal_id in calendar_ids_to_try:
        raw = await asyncio.to_thread(_fetch, cal_id)
        if raw is not None:
            return _parse_event(raw)

    return None


async def list_user_calendars(
    user: User,
    db: AsyncSession,
    account: AccountType = "work",
) -> list[dict]:
    """
    Return the list of calendars accessible by the given account.
    Each item: {"id": str, "summary": str, "primary": bool}
    """
    creds = await _get_valid_credentials(user, account, db)

    def _list() -> list[dict]:
        service = _build_service(creds)
        result = service.calendarList().list().execute()
        items = result.get("items", [])
        return [
            {
                "id": cal.get("id", ""),
                "summary": cal.get("summary", cal.get("id", "")),
                "primary": cal.get("primary", False),
            }
            for cal in items
        ]

    return await asyncio.to_thread(_list)
