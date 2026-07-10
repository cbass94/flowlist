"""
Unit tests for synthesis-time logic (synthesis.py).

All tests are synchronous — synthesis.py is pure Python with no I/O.
Reference day: Monday 2026-07-13 in America/Chicago.

Run: docker compose exec backend pytest tests/test_synthesis.py -v
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.synthesis import (
    compute_synthesis_window,
    is_multiperson_meeting,
)

TZ = ZoneInfo("America/Chicago")
SELF = {"bradlee@trackfly.com", "bradleeduncan@gmail.com"}


def dt(hour: int, minute: int = 0) -> datetime:
    """A timezone-aware datetime on Mon 2026-07-13 in TZ."""
    return datetime(2026, 7, 13, hour, minute, tzinfo=TZ)


def meeting(**overrides) -> dict:
    base = {
        "is_all_day": False,
        "status": "confirmed",
        "event_type": "default",
        "attendees": [
            {"email": "bradlee@trackfly.com", "self": True, "responseStatus": "accepted", "resource": False},
            {"email": "someone@else.com", "self": False, "responseStatus": "accepted", "resource": False},
        ],
    }
    base.update(overrides)
    return base


# ── is_multiperson_meeting ────────────────────────────────────────────────────


def test_meeting_with_another_person_qualifies():
    assert is_multiperson_meeting(meeting(), SELF) is True


def test_solo_event_no_attendees_does_not_qualify():
    assert is_multiperson_meeting(meeting(attendees=[]), SELF) is False


def test_event_with_only_self_does_not_qualify():
    attendees = [
        {"email": "bradlee@trackfly.com", "self": True, "responseStatus": "accepted", "resource": False},
        {"email": "bradleeduncan@gmail.com", "self": False, "responseStatus": "accepted", "resource": False},
    ]
    assert is_multiperson_meeting(meeting(attendees=attendees), SELF) is False


def test_declined_meeting_does_not_qualify():
    attendees = [
        {"email": "bradlee@trackfly.com", "self": True, "responseStatus": "declined", "resource": False},
        {"email": "someone@else.com", "self": False, "responseStatus": "accepted", "resource": False},
    ]
    assert is_multiperson_meeting(meeting(attendees=attendees), SELF) is False


def test_all_day_event_does_not_qualify():
    assert is_multiperson_meeting(meeting(is_all_day=True), SELF) is False


def test_cancelled_event_does_not_qualify():
    assert is_multiperson_meeting(meeting(status="cancelled"), SELF) is False


def test_out_of_office_event_does_not_qualify():
    assert is_multiperson_meeting(meeting(event_type="outOfOffice"), SELF) is False


def test_room_resource_only_does_not_qualify():
    attendees = [
        {"email": "bradlee@trackfly.com", "self": True, "responseStatus": "accepted", "resource": False},
        {"email": "room-4@resource.calendar.google.com", "self": False, "responseStatus": "accepted", "resource": True},
    ]
    assert is_multiperson_meeting(meeting(attendees=attendees), SELF) is False


def test_self_identified_by_email_not_flag():
    # No `self` flag set, but the email is in the self set — still counts as us.
    attendees = [
        {"email": "bradleeduncan@gmail.com", "self": False, "responseStatus": "accepted", "resource": False},
        {"email": "someone@else.com", "self": False, "responseStatus": "accepted", "resource": False},
    ]
    assert is_multiperson_meeting(meeting(attendees=attendees), SELF) is True


# ── compute_synthesis_window ──────────────────────────────────────────────────


def test_window_placed_immediately_after_meeting():
    win = compute_synthesis_window(dt(10, 0), 15, 7, 22, [], TZ)
    assert win == (dt(10, 0), dt(10, 15))


def test_window_skipped_when_it_would_pass_hard_end():
    # Meeting ends 9:50pm; 15 min would run to 10:05pm > 10pm hard limit.
    assert compute_synthesis_window(dt(21, 50), 15, 7, 22, [], TZ) is None


def test_window_allowed_exactly_at_hard_end():
    # Ends 9:45pm → 10:00pm exactly, which is allowed (<=).
    win = compute_synthesis_window(dt(21, 45), 15, 7, 22, [], TZ)
    assert win == (dt(21, 45), dt(22, 0))


def test_window_skipped_before_hard_start():
    # Meeting ends 6:50am, before the 7am hard start.
    assert compute_synthesis_window(dt(6, 50), 15, 7, 22, [], TZ) is None


def test_window_skipped_when_external_event_occupies_slot():
    external = [(dt(10, 5), dt(10, 30))]  # overlaps 10:00–10:15
    assert compute_synthesis_window(dt(10, 0), 15, 7, 22, external, TZ) is None


def test_window_allowed_when_next_event_is_back_to_back_but_not_overlapping():
    # An event starting exactly at 10:15 does not overlap [10:00, 10:15).
    external = [(dt(10, 15), dt(11, 0))]
    win = compute_synthesis_window(dt(10, 0), 15, 7, 22, external, TZ)
    assert win == (dt(10, 0), dt(10, 15))


def test_window_not_blocked_by_the_meeting_itself():
    # The meeting ends at 10:00 (adjacent to the synthesis start) — not a conflict.
    external = [(dt(9, 0), dt(10, 0))]
    win = compute_synthesis_window(dt(10, 0), 15, 7, 22, external, TZ)
    assert win == (dt(10, 0), dt(10, 15))
