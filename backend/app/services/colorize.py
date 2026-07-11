"""
Calendar color-coding logic — pure functions, no I/O, no database, no Google API.

FlowList classifies each timed calendar event into one of four productivity
buckets (a 2×2 of Productive/Unproductive × Attractive/Unattractive) and sets the
Google Calendar event color to match.

This module owns the parts that must be deterministic and unit-testable:
  - which events are eligible to color,
  - a stable content signature (so unchanged events are never re-classified),
  - the state machine that decides whether to color/recolor an event or leave it
    alone (respecting colors the user set by hand).

The AI call and the Google Calendar patch live in the service layer.
"""

from __future__ import annotations

import hashlib
from typing import Literal

# The four productivity buckets (2×2 matrix).
BUCKETS: tuple[str, ...] = ("purposeful", "necessary", "distracting", "unnecessary")

# Default bucket → Google Calendar colorId. User-overridable in Settings.
#   purposeful  = Basil (green, 10)  — productive + attractive
#   necessary   = Peacock (blue, 7)  — productive + unattractive
#   distracting = Tomato (red, 11)   — unproductive + attractive
#   unnecessary = Graphite (gray, 8) — unproductive + unattractive
_DEFAULT_COLOR_MAP: dict[str, str] = {
    "purposeful": "10",
    "necessary": "7",
    "distracting": "11",
    "unnecessary": "8",
}

Action = Literal["skip", "apply", "update", "cede"]


def default_color_map() -> dict[str, str]:
    return dict(_DEFAULT_COLOR_MAP)


def user_declined(event: dict, self_emails: set[str]) -> bool:
    """True if the user's own attendee entry is marked declined."""
    for att in event.get("attendees") or []:
        email = (att.get("email") or "").strip().lower()
        is_self = bool(att.get("self")) or (email != "" and email in self_emails)
        if is_self and att.get("responseStatus") == "declined":
            return True
    return False


def is_colorable(event: dict, self_emails: set[str]) -> bool:
    """
    Eligibility filter: color only timed events the user is actually attending.
    Skips all-day, cancelled, and declined events.
    """
    if event.get("is_all_day"):
        return False
    if event.get("status") == "cancelled":
        return False
    if event.get("start_dt") is None:
        return False
    if user_declined(event, self_emails):
        return False
    return True


def content_signature(event: dict) -> str:
    """
    Stable hash of the fields that affect classification. When this is unchanged
    from the cached record, the event does not need to be re-sent to Claude.
    """
    attendees = "|".join(
        sorted((att.get("email") or "").strip().lower() for att in event.get("attendees") or [])
    )
    start = event.get("start_dt")
    parts = [
        (event.get("summary") or "").strip(),
        attendees,
        (event.get("description") or "").strip(),
        start.isoformat() if start is not None else "",
    ]
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def decide_action(
    current_color: str | None,
    *,
    has_record: bool,
    record_applied_color: str | None,
    record_overridden: bool,
    desired_color: str | None,
) -> Action:
    """
    Decide what to do with an event's color, respecting manual edits.

    current_color:        the event's current Google colorId (None = default/uncolored)
    has_record:           whether FlowList has a color record for this event
    record_applied_color: the colorId FlowList last wrote (if has_record)
    record_overridden:    whether we already ceded control of this event
    desired_color:        the colorId for the event's (re)classified bucket

    Returns:
      apply  — first-time color of an unmanaged, uncolored event
      update — recolor an event we manage because its bucket changed
      cede   — stop managing (a pre-existing or user-changed color)
      skip   — nothing to do
    """
    if not has_record:
        if current_color is None:
            return "apply"
        # Event already has a color we didn't set — respect it.
        return "cede"

    if record_overridden:
        return "skip"

    if current_color != record_applied_color:
        # The user changed the color we set — cede control.
        return "cede"

    if desired_color is not None and desired_color != record_applied_color:
        return "update"

    return "skip"
