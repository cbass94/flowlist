"""
Synthesis-time logic — pure functions, no I/O, no database, no Google API.

"Synthesis time" is a short buffer FlowList books immediately after any meeting
that includes someone other than the user, so they have carved-out time to
process what came out of the meeting before moving on.

Rules enforced here (the rest — fetching events, creating blocks — lives in
calendar_service / scheduler_service):
  - A meeting qualifies only if it is a real, timed event with at least one
    attendee who is NOT the user (and not a room/resource).
  - Meetings the user has declined do not qualify.
  - The synthesis block sits in [meeting_end, meeting_end + duration].
  - It must fit entirely within the hard day limits (default 7am–10pm).
  - It is skipped when those minutes are already occupied by a non-FlowList
    (manual/external) event. FlowList task blocks are excluded from that
    conflict check by the caller, so they get shuffled out of the way instead.

Kept free of async/DB code so it can be tested directly with pytest.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# (start, end) — both timezone-aware datetimes
Interval = tuple[datetime, datetime]

# Google special event types that are not real meetings
_NON_MEETING_EVENT_TYPES = {"outOfOffice", "focusTime", "workingLocation"}


def is_multiperson_meeting(event: dict, self_emails: set[str]) -> bool:
    """
    Return True if `event` is a timed meeting that includes at least one
    attendee other than the user (and the user has not declined it).

    `event` is expected to be a normalized dict (see
    calendar_service._parse_synthesis_event) with keys:
        is_all_day, status, event_type, attendees
    where each attendee is {email, self, responseStatus, resource}.

    `self_emails` is the lowercased set of addresses that count as the user.
    """
    if event.get("is_all_day"):
        return False
    if event.get("status") == "cancelled":
        return False
    if event.get("event_type") in _NON_MEETING_EVENT_TYPES:
        return False

    attendees = event.get("attendees") or []
    if not attendees:
        # No attendees at all = a solo block, not a meeting.
        return False

    # If the user is an attendee and has declined, skip entirely.
    for att in attendees:
        email = (att.get("email") or "").strip().lower()
        is_self = bool(att.get("self")) or (email != "" and email in self_emails)
        if is_self and att.get("responseStatus") == "declined":
            return False

    # Require at least one real other person (not the user, not a resource/room).
    for att in attendees:
        if att.get("resource"):
            continue
        if att.get("self"):
            continue
        email = (att.get("email") or "").strip().lower()
        if email == "" or email in self_emails:
            continue
        return True

    return False


def compute_synthesis_window(
    meeting_end: datetime,
    duration_minutes: int,
    hard_start_hour: int,
    hard_end_hour: int,
    external_busy: list[Interval],
    tz: ZoneInfo,
) -> Interval | None:
    """
    Compute the [start, end] window for a synthesis block following a meeting
    that ends at `meeting_end`, or None if no block should be placed.

    Returns None when:
      - the block would start before the hard earliest hour, or
      - the block would end after the hard latest hour (no shortened block —
        we place the full duration or nothing), or
      - the block would overlap any interval in `external_busy`.

    `external_busy` must contain only non-FlowList (manual/external) busy
    intervals — FlowList task blocks are intentionally excluded so they can be
    shuffled out of the way rather than blocking the synthesis buffer.

    `meeting_end` and all `external_busy` datetimes must be timezone-aware.
    `tz` is the user's timezone, used to apply the hard hour limits.
    """
    start = meeting_end
    end = meeting_end + timedelta(minutes=duration_minutes)

    # Apply hard limits in the user's local timezone, anchored to the local day
    # the block starts on.
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    hard_start_dt = local_start.replace(
        hour=hard_start_hour, minute=0, second=0, microsecond=0
    )
    hard_end_dt = local_start.replace(
        hour=hard_end_hour, minute=0, second=0, microsecond=0
    )

    if local_start < hard_start_dt:
        return None
    if local_end > hard_end_dt:
        return None

    # Conflict check: the meeting itself ends exactly at `start`, so it is
    # adjacent (not overlapping) and never trips this test.
    for busy_start, busy_end in external_busy:
        if start < busy_end and end > busy_start:
            return None

    return (start, end)
