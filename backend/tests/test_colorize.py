"""
Unit tests for calendar color-coding logic (colorize.py).

All tests are synchronous — colorize.py is pure Python with no I/O.

Run: docker compose exec backend pytest tests/test_colorize.py -v
"""

from datetime import datetime, timezone

from app.services.colorize import (
    BUCKETS,
    content_signature,
    decide_action,
    default_color_map,
    is_colorable,
    user_declined,
)

SELF = {"me@work.com", "me@gmail.com"}


def event(**overrides) -> dict:
    base = {
        "id": "evt1",
        "summary": "Sync with team",
        "description": "",
        "start_dt": datetime(2026, 7, 13, 15, 0, tzinfo=timezone.utc),
        "is_all_day": False,
        "status": "confirmed",
        "attendees": [
            {"email": "me@work.com", "self": True, "responseStatus": "accepted", "resource": False},
            {"email": "other@x.com", "self": False, "responseStatus": "accepted", "resource": False},
        ],
        "color_id": None,
    }
    base.update(overrides)
    return base


# ── default_color_map ─────────────────────────────────────────────────────────


def test_default_color_map_covers_all_buckets():
    m = default_color_map()
    assert set(m.keys()) == set(BUCKETS)
    assert m["purposeful"] == "10"
    assert m["necessary"] == "7"
    assert m["distracting"] == "11"
    assert m["unnecessary"] == "8"


# ── eligibility ───────────────────────────────────────────────────────────────


def test_timed_attended_event_is_colorable():
    assert is_colorable(event(), SELF) is True


def test_all_day_event_not_colorable():
    assert is_colorable(event(is_all_day=True), SELF) is False


def test_cancelled_event_not_colorable():
    assert is_colorable(event(status="cancelled"), SELF) is False


def test_declined_event_not_colorable():
    attendees = [
        {"email": "me@work.com", "self": True, "responseStatus": "declined", "resource": False},
        {"email": "other@x.com", "self": False, "responseStatus": "accepted", "resource": False},
    ]
    assert is_colorable(event(attendees=attendees), SELF) is False


def test_user_declined_detects_self_by_email():
    attendees = [
        {"email": "me@gmail.com", "self": False, "responseStatus": "declined", "resource": False},
    ]
    assert user_declined(event(attendees=attendees), SELF) is True


# ── content_signature ─────────────────────────────────────────────────────────


def test_signature_stable_for_same_content():
    assert content_signature(event()) == content_signature(event())


def test_signature_changes_with_title():
    assert content_signature(event()) != content_signature(event(summary="Different"))


def test_signature_changes_with_attendees():
    more = event()["attendees"] + [
        {"email": "third@x.com", "self": False, "responseStatus": "accepted", "resource": False}
    ]
    assert content_signature(event()) != content_signature(event(attendees=more))


# ── decide_action state machine ───────────────────────────────────────────────


def test_apply_when_uncolored_and_unmanaged():
    action = decide_action(
        None, has_record=False, record_applied_color=None,
        record_overridden=False, desired_color="10",
    )
    assert action == "apply"


def test_cede_when_preexisting_manual_color():
    # Event already has a color we never set.
    action = decide_action(
        "5", has_record=False, record_applied_color=None,
        record_overridden=False, desired_color="10",
    )
    assert action == "cede"


def test_cede_when_user_changed_our_color():
    # We set "10" but the event now shows "5" → the user changed it.
    action = decide_action(
        "5", has_record=True, record_applied_color="10",
        record_overridden=False, desired_color="10",
    )
    assert action == "cede"


def test_skip_when_already_overridden():
    action = decide_action(
        "5", has_record=True, record_applied_color="10",
        record_overridden=True, desired_color="10",
    )
    assert action == "skip"


def test_update_when_reclassified_to_new_color():
    # We own it (current == applied) but the bucket/color changed.
    action = decide_action(
        "10", has_record=True, record_applied_color="10",
        record_overridden=False, desired_color="7",
    )
    assert action == "update"


def test_skip_when_managed_and_unchanged():
    action = decide_action(
        "10", has_record=True, record_applied_color="10",
        record_overridden=False, desired_color="10",
    )
    assert action == "skip"
