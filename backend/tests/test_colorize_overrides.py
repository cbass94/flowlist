"""
Unit tests for bucket-override logic (colorize.py).

Covers the parts of the override feature that must be deterministic: how an
event is matched against stored overrides, how a manual Google colour is read
back as intent, and the decide_action state machine that arbitrates between the
classifier, a stored override, and a colour the user just set by hand.

All tests are synchronous — colorize.py is pure Python with no I/O.

Run: docker compose exec backend pytest tests/test_colorize_overrides.py -v
"""

import pytest

from app.services.colorize import (
    BUCKETS,
    decide_action,
    default_color_map,
    normalize_title,
    override_key_candidates,
    resolve_override,
    reverse_bucket,
)

COLORS = default_color_map()
PURPOSEFUL = COLORS["purposeful"]   # "10"
NECESSARY = COLORS["necessary"]     # "7"
DISTRACTING = COLORS["distracting"] # "11"
UNMAPPED = "5"                      # Banana — not assigned to any bucket


# ── normalize_title ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Weekly Sync", "weekly sync"),
        ("  WEEKLY   Sync  ", "weekly sync"),
        ("[FlowList] Weekly Sync", "weekly sync"),
        ("Weekly Sync #12", "weekly sync"),
        ("Standup (3)", "standup"),
        ("Review - 2", "review"),
        ("Launch Review!", "launch review"),
        ("Cafe chat", "cafe chat"),
    ],
)
def test_normalize_title_collapses_noise(raw, expected):
    assert normalize_title(raw) == expected


def test_normalize_title_variants_agree():
    """The whole point: titles a human calls the same meeting share a key."""
    keys = {
        normalize_title("Weekly Sync"),
        normalize_title("weekly sync"),
        normalize_title("[FlowList] Weekly Sync #4"),
        normalize_title("  Weekly  Sync!  "),
    }
    assert len(keys) == 1


def test_normalize_title_keeps_distinct_meetings_apart():
    assert normalize_title("Weekly Sync") != normalize_title("Weekly Review")


def test_normalize_title_strips_accents():
    assert normalize_title("Café Chat") == normalize_title("Cafe Chat")


@pytest.mark.parametrize("raw", [None, "", "   ", "###", "!!!"])
def test_normalize_title_empty_for_meaningless(raw):
    """A key of "" must never be stored or matched — it would match everything."""
    assert normalize_title(raw) == ""


def test_normalize_title_truncated_to_column_width():
    assert len(normalize_title("word " * 200)) <= 255


# ── override_key_candidates / resolve_override ────────────────────────────────


def test_candidates_are_ordered_most_specific_first():
    ev = {"summary": "Weekly Sync", "recurring_event_id": "series-1"}
    assert override_key_candidates(ev, task_id=42) == [
        ("task", "42"),
        ("series", "series-1"),
        ("title", "weekly sync"),
    ]


def test_candidates_omit_absent_identities():
    ev = {"summary": "One-off chat"}
    assert override_key_candidates(ev) == [("title", "one off chat")]


def test_candidates_omit_unusable_title():
    ev = {"summary": "###", "recurring_event_id": "series-1"}
    assert override_key_candidates(ev) == [("series", "series-1")]


def test_task_override_beats_series_and_title():
    ev = {"summary": "Weekly Sync", "recurring_event_id": "series-1"}
    cands = override_key_candidates(ev, task_id=42)
    got = resolve_override(cands, {
        ("task", "42"): "purposeful",
        ("series", "series-1"): "necessary",
        ("title", "weekly sync"): "unnecessary",
    })
    assert got == ("purposeful", "task")


def test_series_override_beats_title():
    ev = {"summary": "Weekly Sync", "recurring_event_id": "series-1"}
    cands = override_key_candidates(ev)
    got = resolve_override(cands, {
        ("series", "series-1"): "necessary",
        ("title", "weekly sync"): "unnecessary",
    })
    assert got == ("necessary", "series")


def test_resolve_override_returns_none_when_unmatched():
    cands = override_key_candidates({"summary": "Weekly Sync"})
    assert resolve_override(cands, {}) is None
    assert resolve_override(cands, {("title", "other meeting"): "necessary"}) is None


# ── reverse_bucket ────────────────────────────────────────────────────────────


def test_reverse_bucket_reads_a_mapped_colour():
    assert reverse_bucket(DISTRACTING, COLORS) == "distracting"
    assert reverse_bucket(PURPOSEFUL, COLORS) == "purposeful"


@pytest.mark.parametrize("colour", [None, "", UNMAPPED])
def test_reverse_bucket_none_for_unmapped(colour):
    assert reverse_bucket(colour, COLORS) is None


def test_reverse_bucket_round_trips_every_bucket():
    for bucket in BUCKETS:
        assert reverse_bucket(COLORS[bucket], COLORS) == bucket


def test_reverse_bucket_is_deterministic_when_colours_collide():
    """Nothing stops two buckets sharing a colour; the answer must be stable."""
    shared = dict(COLORS, necessary="10", purposeful="10")
    assert reverse_bucket("10", shared) == reverse_bucket("10", shared) == "purposeful"


# ── decide_action: the classifier's normal path ───────────────────────────────


def unmanaged(**kw):
    base = dict(has_record=False, record_applied_color=None, record_overridden=False)
    base.update(kw)
    return base


def managed(applied, **kw):
    base = dict(has_record=True, record_applied_color=applied, record_overridden=False)
    base.update(kw)
    return base


def test_apply_colours_an_untouched_event():
    assert decide_action(None, **unmanaged(desired_color=NECESSARY)) == "apply"


def test_update_recolours_a_managed_event():
    action = decide_action(
        NECESSARY, **managed(NECESSARY, desired_color=PURPOSEFUL)
    )
    assert action == "update"


def test_skip_when_already_the_desired_colour():
    assert decide_action(NECESSARY, **managed(NECESSARY, desired_color=NECESSARY)) == "skip"


def test_skip_when_nothing_is_wanted():
    assert decide_action(None, **unmanaged(desired_color=None)) == "skip"


# ── decide_action: manual edits become intent ─────────────────────────────────


def test_manual_edit_to_a_mapped_colour_is_adopted():
    """The user recoloured an event we manage — learn it, don't just give up."""
    action = decide_action(
        DISTRACTING,
        **managed(NECESSARY, desired_color=NECESSARY, adoptable=True),
    )
    assert action == "adopt"


def test_manual_edit_to_an_unmapped_colour_still_cedes():
    """Regression: a colour meaning no bucket keeps the original behaviour."""
    action = decide_action(
        UNMAPPED,
        **managed(NECESSARY, desired_color=NECESSARY, adoptable=False),
    )
    assert action == "cede"


def test_pre_existing_mapped_colour_is_adopted():
    action = decide_action(
        DISTRACTING, **unmanaged(desired_color=NECESSARY, adoptable=True)
    )
    assert action == "adopt"


def test_pre_existing_unmapped_colour_cedes():
    action = decide_action(
        UNMAPPED, **unmanaged(desired_color=NECESSARY, adoptable=False)
    )
    assert action == "cede"


# ── decide_action: recovering events ceded before overrides existed ───────────


def test_previously_ceded_event_with_mapped_colour_is_recovered():
    action = decide_action(
        DISTRACTING,
        has_record=True,
        record_applied_color=DISTRACTING,
        record_overridden=True,
        desired_color=NECESSARY,
        adoptable=True,
    )
    assert action == "adopt"


def test_previously_ceded_event_with_unmapped_colour_is_left_alone():
    """A per-event exception the user painted by hand outranks any override."""
    action = decide_action(
        UNMAPPED,
        has_record=True,
        record_applied_color=UNMAPPED,
        record_overridden=True,
        desired_color=NECESSARY,
        adoptable=False,
    )
    assert action == "skip"


# ── decide_action: overrides drive the colour ─────────────────────────────────


def test_override_colours_a_new_event():
    """desired_color carries the override; an unseen event just gets painted."""
    assert decide_action(None, **unmanaged(desired_color=DISTRACTING)) == "apply"


def test_override_change_repaints_a_managed_event():
    action = decide_action(
        NECESSARY, **managed(NECESSARY, desired_color=DISTRACTING)
    )
    assert action == "update"


def test_adopt_settles_on_the_next_run():
    """
    Adoption must converge, or the colorizer would rewrite the same event every
    hour. After adopting, applied == current == desired, so the next run skips.
    """
    first = decide_action(
        DISTRACTING, **managed(NECESSARY, desired_color=NECESSARY, adoptable=True)
    )
    assert first == "adopt"
    # Post-adopt state: we stored their colour, and the override now drives it.
    second = decide_action(
        DISTRACTING, **managed(DISTRACTING, desired_color=DISTRACTING, adoptable=True)
    )
    assert second == "skip"


def test_cede_settles_on_the_next_run():
    first = decide_action(
        UNMAPPED, **managed(NECESSARY, desired_color=NECESSARY, adoptable=False)
    )
    assert first == "cede"
    second = decide_action(
        UNMAPPED,
        has_record=True,
        record_applied_color=UNMAPPED,
        record_overridden=True,
        desired_color=NECESSARY,
        adoptable=False,
    )
    assert second == "skip"
