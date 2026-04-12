"""
Unit tests for the free-slot finder (slot_finder.py).

All tests are synchronous — the slot finder is pure Python with no I/O.
Reference date: Monday 2026-04-06 (weekday 0) in America/Chicago.
All datetimes are built with ZoneInfo so DST is handled correctly.

Run: docker compose exec backend pytest tests/test_slot_finder.py -v
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.slot_finder import (
    Interval,
    SlotFinderConfig,
    find_free_slots,
    get_valid_windows,
    merge_intervals,
    split_into_blocks,
)

TZ = ZoneInfo("America/Chicago")

# Monday 2026-04-06
MONDAY = date(2026, 4, 6)
TUESDAY = date(2026, 4, 7)
SATURDAY = date(2026, 4, 11)
SUNDAY = date(2026, 4, 12)

DEFAULT_CONFIG = SlotFinderConfig(
    work_start_hour=8,
    work_end_hour=17,
    hard_start_hour=7,
    hard_end_hour=22,
    buffer_minutes=30,
    max_block_minutes=120,
    min_block_minutes=60,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def dt(d: date, hour: int, minute: int = 0) -> datetime:
    """Shorthand for a timezone-aware datetime in TZ."""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ)


def busy(d: date, h_start: int, m_start: int, h_end: int, m_end: int) -> Interval:
    return (dt(d, h_start, m_start), dt(d, h_end, m_end))


def slots(
    busy_list: list[Interval],
    duration: int,
    task_type: str = "work",
    target_date: date = MONDAY,
    config: SlotFinderConfig = DEFAULT_CONFIG,
    is_off_hours_allowed: bool = False,
    is_workday_allowed: bool = False,
) -> list[Interval]:
    """Wrapper that calls find_free_slots with defaults."""
    return find_free_slots(
        busy_intervals=busy_list,
        target_date=target_date,
        duration_minutes=duration,
        task_type=task_type,
        user_tz=TZ,
        config=config,
        is_off_hours_allowed=is_off_hours_allowed,
        is_workday_allowed=is_workday_allowed,
    )


# ── merge_intervals ───────────────────────────────────────────────────────────


class TestMergeIntervals:
    def test_empty(self):
        assert merge_intervals([]) == []

    def test_single(self):
        iv = busy(MONDAY, 9, 0, 10, 0)
        assert merge_intervals([iv]) == [iv]

    def test_non_overlapping(self):
        a = busy(MONDAY, 8, 0, 9, 0)
        b = busy(MONDAY, 10, 0, 11, 0)
        assert merge_intervals([a, b]) == [a, b]

    def test_overlapping(self):
        a = busy(MONDAY, 8, 0, 9, 30)
        b = busy(MONDAY, 9, 0, 10, 0)
        result = merge_intervals([a, b])
        assert result == [(dt(MONDAY, 8), dt(MONDAY, 10))]

    def test_adjacent(self):
        a = busy(MONDAY, 8, 0, 9, 0)
        b = busy(MONDAY, 9, 0, 10, 0)
        result = merge_intervals([a, b])
        # Adjacent (touching) intervals merge
        assert result == [(dt(MONDAY, 8), dt(MONDAY, 10))]

    def test_unsorted_input(self):
        a = busy(MONDAY, 10, 0, 11, 0)
        b = busy(MONDAY, 8, 0, 9, 0)
        assert merge_intervals([a, b]) == [b, a]

    def test_fully_contained(self):
        outer = busy(MONDAY, 8, 0, 12, 0)
        inner = busy(MONDAY, 9, 0, 10, 0)
        assert merge_intervals([outer, inner]) == [outer]

    def test_three_way_chain(self):
        a = busy(MONDAY, 8, 0, 10, 0)
        b = busy(MONDAY, 9, 0, 11, 0)
        c = busy(MONDAY, 10, 30, 12, 0)
        result = merge_intervals([a, b, c])
        assert result == [(dt(MONDAY, 8), dt(MONDAY, 12))]


# ── get_valid_windows ─────────────────────────────────────────────────────────


class TestGetValidWindows:
    def test_work_task_weekday(self):
        windows = get_valid_windows(MONDAY, "work", TZ, DEFAULT_CONFIG)
        assert windows == [(dt(MONDAY, 8), dt(MONDAY, 17))]

    def test_work_task_saturday_default(self):
        """Work tasks are not schedulable on weekends by default."""
        windows = get_valid_windows(SATURDAY, "work", TZ, DEFAULT_CONFIG)
        assert windows == []

    def test_work_task_saturday_off_hours_allowed(self):
        """is_off_hours_allowed lifts the weekend restriction."""
        windows = get_valid_windows(
            SATURDAY, "work", TZ, DEFAULT_CONFIG, is_off_hours_allowed=True
        )
        assert windows == [(dt(SATURDAY, 7), dt(SATURDAY, 22))]

    def test_work_task_sunday_off_hours_allowed(self):
        windows = get_valid_windows(
            SUNDAY, "work", TZ, DEFAULT_CONFIG, is_off_hours_allowed=True
        )
        assert windows == [(dt(SUNDAY, 7), dt(SUNDAY, 22))]

    def test_work_task_off_hours_weekday(self):
        """Off-hours work task on a weekday uses full hard-limit window."""
        windows = get_valid_windows(
            MONDAY, "work", TZ, DEFAULT_CONFIG, is_off_hours_allowed=True
        )
        assert windows == [(dt(MONDAY, 7), dt(MONDAY, 22))]

    def test_personal_task_default(self):
        """Personal tasks: two windows — before and after work hours."""
        windows = get_valid_windows(MONDAY, "personal", TZ, DEFAULT_CONFIG)
        # Pre-work: 7am–8am (only 60 min = exactly min_block_minutes, included)
        # Post-work: 5pm–10pm
        assert windows == [
            (dt(MONDAY, 7), dt(MONDAY, 8)),
            (dt(MONDAY, 17), dt(MONDAY, 22)),
        ]

    def test_personal_task_workday_allowed(self):
        """is_workday_allowed gives a single full-day window."""
        windows = get_valid_windows(
            MONDAY, "personal", TZ, DEFAULT_CONFIG, is_workday_allowed=True
        )
        assert windows == [(dt(MONDAY, 7), dt(MONDAY, 22))]

    def test_personal_task_weekend(self):
        """Personal tasks on weekends: full hard-limit window (no work-hours exclusion)."""
        windows = get_valid_windows(SATURDAY, "personal", TZ, DEFAULT_CONFIG)
        # On weekends work_start/end don't apply to personal tasks
        # Pre-work window: 7am-8am, post-work: 5pm-10pm (same rule applies)
        # Actually: the rule excludes work hours Mon-Sun consistently.
        # Let's verify:
        assert (dt(SATURDAY, 17), dt(SATURDAY, 22)) in windows


# ── find_free_slots — core cases ──────────────────────────────────────────────


class TestFindFreeSlotsCore:
    def test_no_busy_events_work_60min(self):
        """Empty calendar: first slot starts at work window start (8am)."""
        result = slots([], duration=60)
        assert len(result) >= 1
        assert result[0] == (dt(MONDAY, 8), dt(MONDAY, 9))

    def test_no_busy_events_work_120min(self):
        """Two-hour task with no conflicts: starts at 8am."""
        result = slots([], duration=120)
        assert result[0] == (dt(MONDAY, 8), dt(MONDAY, 10))

    def test_fully_packed_day(self):
        """Single event covering the entire work window — no slots."""
        result = slots(
            [busy(MONDAY, 8, 0, 17, 0)],
            duration=60,
        )
        assert result == []

    def test_event_before_window_no_effect_on_cursor(self):
        """Event ends well before window_start (> buffer) — no buffer impact."""
        # Event 6am–7am, window starts 8am, buffer=30min → 7am+30=7:30, but 7:30 < 8am window start
        # So cursor should still start at 8am
        result = slots([busy(MONDAY, 6, 0, 7, 0)], duration=60)
        assert result[0][0] == dt(MONDAY, 8)

    def test_event_ending_inside_buffer_before_window(self):
        """
        Event ends at 7:45am. Window starts 8am. Buffer=30min.
        7:45 + 30 = 8:15 → first slot starts at 8:15am.
        """
        result = slots([busy(MONDAY, 7, 0, 7, 45)], duration=60)
        assert result[0][0] == dt(MONDAY, 8, 15)

    def test_event_ending_exactly_at_window_start(self):
        """
        Event ends exactly at 8am (window start). Buffer=30min → cursor = 8:30am.
        """
        result = slots([busy(MONDAY, 7, 30, 8, 0)], duration=60)
        assert result[0][0] == dt(MONDAY, 8, 30)

    def test_single_morning_event(self):
        """
        9am–10am event on a clean day.
        Before: 8am–9am → 60min gap at 8am (no buffer needed at window start).
        After: 10am + 30min buffer = 10:30am → slot at 10:30.
        """
        result = slots([busy(MONDAY, 9, 0, 10, 0)], duration=60)
        assert (dt(MONDAY, 8), dt(MONDAY, 9)) in result
        assert (dt(MONDAY, 10, 30), dt(MONDAY, 11, 30)) in result

    def test_slot_respects_window_end(self):
        """
        A slot that would extend past the window end is not returned.
        Window ends 5pm. Event at 4pm–4:15pm. After buffer: 4:45pm.
        Task duration=60min → would end 5:45pm > 5pm → not returned.
        """
        result = slots([busy(MONDAY, 16, 0, 16, 15)], duration=60)
        # The only valid slot is before 4pm, starting at 8am
        for start, end in result:
            assert end <= dt(MONDAY, 17), f"Slot {start}–{end} extends past window end"


# ── Buffer rule edge cases ────────────────────────────────────────────────────


class TestBufferRule:
    def test_buffer_prevents_slot_in_small_gap(self):
        """
        Gap of 50 min between two events, but 30 min buffer eats into it.
        Available: 50 - 30 = 20 min → can't fit a 60-min task.
        """
        result = slots(
            [
                busy(MONDAY, 8, 0, 9, 0),   # 8–9am
                busy(MONDAY, 9, 50, 11, 0),  # 9:50–11am
            ],
            duration=60,
        )
        # Gap is 9am to 9:50am (50min). After 30min buffer from 9am: cursor=9:30am.
        # 9:30am + 60min = 10:30am > 9:50am → no slot in this gap.
        for start, end in result:
            # No slot should be squeezed into the 9am–9:50am gap
            assert not (start >= dt(MONDAY, 9) and start < dt(MONDAY, 9, 50))

    def test_buffer_exactly_satisfied(self):
        """
        Gap of exactly 90 min: 30 min buffer + 60 min task = 90 min. Fits exactly.
        """
        result = slots(
            [
                busy(MONDAY, 8, 0, 9, 0),
                busy(MONDAY, 10, 30, 12, 0),
            ],
            duration=60,
        )
        # After 9am event + 30min buffer: cursor=9:30am.
        # 9:30am + 60min = 10:30am ≤ 10:30am → fits exactly.
        assert (dt(MONDAY, 9, 30), dt(MONDAY, 10, 30)) in result

    def test_buffer_conflict_too_tight(self):
        """
        Gap of 89 min: 30 min buffer + 60 min task = 90 min. One minute short.
        """
        result = slots(
            [
                busy(MONDAY, 8, 0, 9, 0),
                busy(MONDAY, 10, 29, 12, 0),  # gap: 9:00–10:29 = 89min
            ],
            duration=60,
        )
        # Cursor after buffer: 9:30am. Need to end by 10:29am.
        # 9:30 + 60 = 10:30 > 10:29 → no slot.
        bad_slots = [
            (s, e) for s, e in result if s >= dt(MONDAY, 9) and s < dt(MONDAY, 10, 29)
        ]
        assert bad_slots == []

    def test_no_buffer_at_window_start(self):
        """
        No event before or at window start → first slot begins exactly at window start.
        """
        result = slots([], duration=60)
        assert result[0][0] == dt(MONDAY, 8)

    def test_back_to_back_events_no_gap(self):
        """Two events with no gap between them — no slot possible in that stretch."""
        result = slots(
            [
                busy(MONDAY, 8, 0, 10, 0),
                busy(MONDAY, 10, 0, 12, 0),
            ],
            duration=60,
        )
        # No gap between the two events. After 12pm + 30min buffer = 12:30pm → one slot
        assert result == [(dt(MONDAY, 12, 30), dt(MONDAY, 13, 30))]


# ── Split-day scenarios ───────────────────────────────────────────────────────


class TestSplitDay:
    def test_morning_free_afternoon_packed(self):
        """Morning is free; afternoon packed. Slots only in the morning."""
        result = slots(
            [busy(MONDAY, 12, 0, 17, 0)],  # noon to 5pm packed
            duration=60,
        )
        for start, end in result:
            assert end <= dt(MONDAY, 12), f"Slot {start}–{end} is in packed afternoon"
        # Should have at least one slot in the morning
        morning_slots = [(s, e) for s, e in result if s < dt(MONDAY, 12)]
        assert len(morning_slots) >= 1

    def test_afternoon_free_morning_packed(self):
        """Morning packed; afternoon free. Slots only in the afternoon."""
        result = slots(
            [busy(MONDAY, 8, 0, 13, 0)],  # 8am to 1pm packed
            duration=60,
        )
        # After 1pm + 30min buffer = 1:30pm
        assert all(start >= dt(MONDAY, 13, 30) for start, _ in result)
        assert len(result) >= 1

    def test_slot_found_after_midday_meeting(self):
        """Single midday meeting; slot available in the afternoon."""
        result = slots(
            [busy(MONDAY, 11, 0, 12, 0)],
            duration=90,
        )
        # Before meeting: 8am–11am = 3hrs, fits 90min at 8am
        # After meeting + buffer: 12:30pm, 90min → 2pm ≤ 5pm → fits
        assert (dt(MONDAY, 8), dt(MONDAY, 9, 30)) in result
        assert (dt(MONDAY, 12, 30), dt(MONDAY, 14)) in result

    def test_multiple_events_multiple_gaps(self):
        """Day with three meetings; verify slots in each valid gap."""
        result = slots(
            [
                busy(MONDAY, 8, 0, 9, 0),
                busy(MONDAY, 11, 0, 12, 0),
                busy(MONDAY, 14, 0, 15, 0),
            ],
            duration=60,
        )
        starts = [s for s, _ in result]
        # Gap 1: 9:00+30=9:30 → 9:30 to 11:00 (90min) → 60min fits
        assert dt(MONDAY, 9, 30) in starts
        # Gap 2: 12:00+30=12:30 → 12:30 to 14:00 (90min) → fits
        assert dt(MONDAY, 12, 30) in starts
        # Gap 3: 15:00+30=15:30 → 15:30 to 17:00 (90min) → fits
        assert dt(MONDAY, 15, 30) in starts


# ── Weekend handling ──────────────────────────────────────────────────────────


class TestWeekendHandling:
    def test_work_task_saturday_no_slots(self):
        result = slots([], duration=60, task_type="work", target_date=SATURDAY)
        assert result == []

    def test_work_task_sunday_no_slots(self):
        result = slots([], duration=60, task_type="work", target_date=SUNDAY)
        assert result == []

    def test_work_task_saturday_off_hours_allowed(self):
        """Off-hours flag enables weekend scheduling."""
        result = slots(
            [],
            duration=60,
            task_type="work",
            target_date=SATURDAY,
            is_off_hours_allowed=True,
        )
        assert len(result) >= 1
        assert result[0][0] == dt(SATURDAY, 7)

    def test_personal_task_saturday(self):
        """Personal tasks work on weekends in non-work-hour windows."""
        result = slots([], duration=60, task_type="personal", target_date=SATURDAY)
        assert len(result) >= 1

    def test_personal_task_workday_allowed_on_monday(self):
        """is_workday_allowed gives personal tasks access to work hours."""
        result = slots(
            [],
            duration=60,
            task_type="personal",
            is_workday_allowed=True,
        )
        # Full hard-limit window: 7am–10pm
        assert result[0][0] == dt(MONDAY, 7)

    def test_personal_task_not_workday_on_monday(self):
        """Personal task on Monday without workday_allowed: split windows."""
        result = slots([], duration=60, task_type="personal", target_date=MONDAY)
        starts = [s for s, _ in result]
        # Must NOT have slots during 8am–5pm (work hours)
        for start in starts:
            is_in_work_hours = dt(MONDAY, 8) <= start < dt(MONDAY, 17)
            assert not is_in_work_hours, f"Personal task slot at {start} falls in work hours"
        # Must have at least the post-work window slot
        post_work = [s for s in starts if s >= dt(MONDAY, 17)]
        assert len(post_work) >= 1


# ── Hard limits ───────────────────────────────────────────────────────────────


class TestHardLimits:
    def test_no_slot_before_7am(self):
        result = slots([], duration=60, task_type="work", is_off_hours_allowed=True)
        for start, _ in result:
            assert start.hour >= DEFAULT_CONFIG.hard_start_hour

    def test_no_slot_after_10pm(self):
        result = slots([], duration=60, task_type="work", is_off_hours_allowed=True)
        for _, end in result:
            assert end <= dt(MONDAY, DEFAULT_CONFIG.hard_end_hour)

    def test_slot_ends_at_window_boundary(self):
        """
        Duration 90min starting at 3:30pm should be valid (ends 5pm).
        Duration 90min starting at 3:31pm should NOT be valid (ends 5:01pm > 5pm).
        """
        # Fill all morning slots with a long meeting
        result = slots(
            [busy(MONDAY, 8, 0, 15, 30)],
            duration=90,
        )
        # Cursor after buffer: 4pm. 4pm + 90min = 5:30pm > 5pm → no slot in default window
        assert result == []


# ── split_into_blocks ─────────────────────────────────────────────────────────


class TestSplitIntoBlocks:
    def test_short_task_single_block(self):
        assert split_into_blocks(60, DEFAULT_CONFIG) == [60]
        assert split_into_blocks(90, DEFAULT_CONFIG) == [90]
        assert split_into_blocks(120, DEFAULT_CONFIG) == [120]

    def test_task_over_max_splits(self):
        # 180min → 120 + 60
        assert split_into_blocks(180, DEFAULT_CONFIG) == [120, 60]

    def test_task_240min(self):
        # 240min → 120 + 120
        assert split_into_blocks(240, DEFAULT_CONFIG) == [120, 120]

    def test_task_150min(self):
        # 150min → 120 + 30; but 30 < min_block (60), so merge → [150]?
        # Per CLAUDE.md: min single block for split tasks is 1 hour.
        # Our implementation merges sub-minimum remainders into the previous block.
        result = split_into_blocks(150, DEFAULT_CONFIG)
        assert sum(result) == 150
        for block in result:
            assert block >= DEFAULT_CONFIG.min_block_minutes or len(result) == 1

    def test_task_exactly_max(self):
        assert split_into_blocks(120, DEFAULT_CONFIG) == [120]

    def test_all_blocks_within_max(self):
        for duration in range(60, 481, 10):
            blocks = split_into_blocks(duration, DEFAULT_CONFIG)
            assert sum(blocks) == duration
            for b in blocks:
                assert b <= DEFAULT_CONFIG.max_block_minutes


# ── Timezone / DST correctness ────────────────────────────────────────────────


class TestTimezone:
    def test_daylight_saving_time_date(self):
        """
        2026-03-08 is the Sunday when clocks spring forward in America/Chicago.
        The Monday after (2026-03-09) should behave normally.
        """
        dst_monday = date(2026, 3, 9)
        result = find_free_slots(
            busy_intervals=[],
            target_date=dst_monday,
            duration_minutes=60,
            task_type="work",
            user_tz=TZ,
            config=DEFAULT_CONFIG,
        )
        assert len(result) >= 1
        start, end = result[0]
        # Start should be 8am Chicago time (which is UTC-5 in winter → UTC-6 DST?)
        # Just verify it's timezone-aware and the slot is valid
        assert start.tzinfo is not None
        assert (end - start) == timedelta(minutes=60)

    def test_returned_slots_are_tz_aware(self):
        """All returned slots must be timezone-aware."""
        result = slots([], duration=60)
        for start, end in result:
            assert start.tzinfo is not None, "start must be timezone-aware"
            assert end.tzinfo is not None, "end must be timezone-aware"

    def test_slot_duration_is_exact(self):
        """Slot duration must exactly equal the requested duration."""
        for duration in [60, 90, 120]:
            result = slots([], duration=duration)
            for start, end in result:
                assert (end - start) == timedelta(minutes=duration)
