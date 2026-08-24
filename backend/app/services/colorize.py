"""
Calendar color-coding logic — pure functions, no I/O, no database, no Google API.

FlowList classifies each timed calendar event into one of four productivity
buckets (a 2×2 of Productive/Unproductive × Attractive/Unattractive) and sets the
Google Calendar event color to match.

This module owns the parts that must be deterministic and unit-testable:
  - which events are eligible to color,
  - a stable content signature (so unchanged events are never re-classified),
  - how an event is matched against the user's stored bucket overrides,
  - the state machine that decides whether to color/recolor an event or leave it
    alone (respecting colors the user set by hand).

The AI call and the Google Calendar patch live in the service layer.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
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

Action = Literal["skip", "apply", "update", "cede", "adopt"]

# Override match scopes, most specific first. See override_key_candidates.
SCOPES: tuple[str, ...] = ("task", "series", "title")


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


# Characters that carry no classification meaning but vary freely between
# otherwise-identical events (emoji, brackets, punctuation, separators).
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
# Trailing instance markers: "Weekly Sync #12", "Standup (3)", "Review - 2".
_TRAILING_INDEX_RE = re.compile(r"[\s\-–—]*[#(\[]?\d+[)\]]?\s*$")
_WS_RE = re.compile(r"\s+")


def normalize_title(summary: str | None) -> str:
    """
    Reduce an event title to a stable key, so that events a human would call
    "the same meeting" collapse to the same string.

    Deliberately conservative: it strips formatting noise, not words. Dropping
    words (a trailing attendee name, say) would make unrelated meetings collide,
    and a title override that matches too much is worse than one that matches too
    little — a missed match just means the event gets classified normally.

    Removes the [FlowList] tag, emoji and punctuation, a trailing instance number
    ("Weekly Sync #12" -> "weekly sync"), and case/whitespace variation.
    Returns "" for a title with nothing left, which never matches.
    """
    if not summary:
        return ""
    text = summary.replace("[FlowList]", " ")
    # Normalize accents/width so "Café" and "Cafe" don't split a rule in two.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _TRAILING_INDEX_RE.sub("", text)
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    # match_key is String(255); a title longer than that is truncated on both
    # the write and the lookup path, so the two still agree.
    return text[:255]


def override_key_candidates(
    event: dict, task_id: int | None = None
) -> list[tuple[str, str]]:
    """
    The (scope, match_key) pairs this event could be matched by, most specific
    first: the task it belongs to, then its recurring series, then its title.

    Order is the precedence — resolve_override takes the first that hits, so a
    per-task correction beats a series rule, which beats a title rule.
    """
    candidates: list[tuple[str, str]] = []
    if task_id is not None:
        candidates.append(("task", str(task_id)))
    series_id = event.get("recurring_event_id")
    if series_id:
        candidates.append(("series", str(series_id)[:255]))
    title_key = normalize_title(event.get("summary"))
    if title_key:
        candidates.append(("title", title_key))
    return candidates


def resolve_override(
    candidates: list[tuple[str, str]],
    overrides: dict[tuple[str, str], str],
) -> tuple[str, str] | None:
    """
    First matching override for these candidates, as (bucket, scope).
    None when the user has expressed no preference for this event.
    """
    for scope, key in candidates:
        bucket = overrides.get((scope, key))
        if bucket is not None:
            return bucket, scope
    return None


def reverse_bucket(color_id: str | None, color_map: dict[str, str]) -> str | None:
    """
    Read a Google colorId back as a bucket, inverting the user's color map.

    This is what lets a manual recolor in Google Calendar be understood as
    intent rather than just a refusal. A color the user hasn't assigned to any
    bucket says nothing about buckets, and returns None.

    Ambiguity is possible — nothing stops two buckets sharing a color — so
    resolution follows BUCKETS order for a stable, predictable answer.
    """
    if not color_id:
        return None
    for bucket in BUCKETS:
        if color_map.get(bucket) == color_id:
            return bucket
    return None


def decide_action(
    current_color: str | None,
    *,
    has_record: bool,
    record_applied_color: str | None,
    record_overridden: bool,
    desired_color: str | None,
    adoptable: bool = False,
) -> Action:
    """
    Decide what to do with an event's color, respecting manual edits.

    current_color:        the event's current Google colorId (None = default/uncolored)
    has_record:           whether FlowList has a color record for this event
    record_applied_color: the colorId FlowList last wrote (if has_record)
    record_overridden:    whether we already ceded control of this event
    desired_color:        the colorId FlowList wants — from the user's override
                          when one matched, otherwise from the classification
    adoptable:            whether current_color maps back to a bucket
                          (reverse_bucket found one), i.e. whether a manual edit
                          can be read as intent

    Returns:
      apply  — first-time color of an unmanaged, uncolored event
      update — recolor an event we manage because its desired bucket changed
      adopt  — learn the color the user chose as a durable bucket override
      cede   — stop managing (a color we cannot interpret as a bucket)
      skip   — nothing to do

    The branches are ordered by whose signal is newest, because that is what
    makes the feature feel obedient: a color the user just set outranks a stored
    override, which outranks the classifier.

    Note that desired_color carries the override implicitly — the caller resolves
    it — so there is no separate has_override flag to keep in sync.
    """
    if has_record and record_overridden:
        # An event we previously ceded. Reconsider it once: if the color the
        # user chose means something, recover it as a real override (this is how
        # cedes recorded before overrides existed get their meaning back).
        # Otherwise they want something FlowList has no name for — leave it be,
        # permanently, even if an override would otherwise match.
        return "adopt" if adoptable else "skip"

    if has_record and current_color != record_applied_color:
        # The color changed out from under us: a manual edit since our last write.
        return "adopt" if adoptable else "cede"

    if not has_record and current_color is not None:
        # Pre-existing color on an event we have never managed.
        return "adopt" if adoptable else "cede"

    if desired_color is None or current_color == desired_color:
        return "skip"

    return "update" if has_record else "apply"
