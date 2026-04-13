"""
Free-slot finder — pure functions, no I/O, no database, no Google API.

All scheduling rules from CLAUDE.md are enforced here:
  - Work tasks: Mon–Fri, work_start–work_end (unless is_off_hours_allowed)
  - Personal tasks: hard_start–hard_end, excluding work hours (unless is_workday_allowed)
  - Hard limits: nothing before hard_start_hour or after hard_end_hour
  - Buffer: 30 min of clear time REQUIRED before each auto-scheduled block
  - Max block: 2 hours; min split block: 1 hour

This module is kept free of async/DB code so it can be tested directly
with `pytest` and no mocking.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

# (start, end) — both timezone-aware datetimes
Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class SlotFinderConfig:
    work_start_hour: int = 8
    work_end_hour: int = 17
    hard_start_hour: int = 7
    hard_end_hour: int = 22
    buffer_minutes: int = 30
    max_block_minutes: int = 120
    min_block_minutes: int = 60
    allow_work_on_weekends: bool = False
    allow_personal_on_weekends: bool = True


TaskType = Literal["work", "personal"]


# ── Internal helpers ─────────────────────────────────────────────────────────


def _local(d: date, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """Build a timezone-aware datetime from date parts + hour + minute."""
    return datetime(d.year, d.month, d.day, hour, minute, 0, 0, tzinfo=tz)


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5=Sat, 6=Sun


# ── Public: interval utilities ────────────────────────────────────────────────


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """
    Merge overlapping or adjacent intervals. Returns a sorted, non-overlapping list.

    Example:
        [(8:00,9:00), (8:30,10:00), (12:00,13:00)] → [(8:00,10:00), (12:00,13:00)]
    """
    if not intervals:
        return []
    sorted_ivs = sorted(intervals, key=lambda iv: iv[0])
    merged: list[Interval] = [sorted_ivs[0]]
    for start, end in sorted_ivs[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


# ── Public: valid-window builder ──────────────────────────────────────────────


def get_valid_windows(
    target_date: date,
    task_type: TaskType,
    user_tz: ZoneInfo,
    config: SlotFinderConfig,
    is_off_hours_allowed: bool = False,
    is_workday_allowed: bool = False,
) -> list[Interval]:
    """
    Return the list of time windows within which an auto-block may be placed
    on `target_date`, respecting task type and override flags.

    Work tasks:
      - Default: Mon–Fri, work_start → work_end
      - is_off_hours_allowed: hard_start → hard_end (any day)

    Personal tasks:
      - Default: two windows — [hard_start, work_start] and [work_end, hard_end]
        (keeps personal tasks out of work hours)
      - is_workday_allowed: hard_start → hard_end (full day, any day)

    Windows shorter than config.min_block_minutes are discarded.
    """
    min_window = timedelta(minutes=config.min_block_minutes)

    if task_type == "work":
        if _is_weekend(target_date) and not is_off_hours_allowed and not config.allow_work_on_weekends:
            return []
        if is_off_hours_allowed:
            start = _local(target_date, config.hard_start_hour, 0, user_tz)
            end = _local(target_date, config.hard_end_hour, 0, user_tz)
        else:
            start = _local(target_date, config.work_start_hour, 0, user_tz)
            end = _local(target_date, config.work_end_hour, 0, user_tz)
        return [(start, end)] if end - start >= min_window else []

    # personal
    if _is_weekend(target_date) and not config.allow_personal_on_weekends and not is_workday_allowed:
        return []

    hard_start = _local(target_date, config.hard_start_hour, 0, user_tz)
    hard_end = _local(target_date, config.hard_end_hour, 0, user_tz)

    if is_workday_allowed:
        return [(hard_start, hard_end)] if hard_end - hard_start >= min_window else []

    # Split into pre-work and post-work windows
    work_start = _local(target_date, config.work_start_hour, 0, user_tz)
    work_end = _local(target_date, config.work_end_hour, 0, user_tz)
    windows: list[Interval] = []

    pre = (hard_start, work_start)
    if pre[1] - pre[0] >= min_window:
        windows.append(pre)

    post = (work_end, hard_end)
    if post[1] - post[0] >= min_window:
        windows.append(post)

    return windows


# ── Public: free-slot finder ──────────────────────────────────────────────────


def find_free_slots(
    busy_intervals: list[Interval],
    target_date: date,
    duration_minutes: int,
    task_type: TaskType,
    user_tz: ZoneInfo,
    config: SlotFinderConfig,
    is_off_hours_allowed: bool = False,
    is_workday_allowed: bool = False,
    min_start: datetime | None = None,
) -> list[Interval]:
    """
    Return all (start, end) slots on `target_date` where a block of
    `duration_minutes` can be placed.

    `busy_intervals` should contain ALL known-busy periods for the day
    (Google Calendar freebusy for both work and personal calendars, merged).
    Including periods that extend before or after the valid window ensures
    correct buffer calculation at window boundaries.

    The buffer rule: 30 min of clear calendar time REQUIRED before each
    auto-block. No buffer is required at the very start of a window when
    there is no preceding event within the buffer window.

    `min_start`: if given, no slot may begin before this datetime. Used by
    the scheduler to skip past-times on the current day without skipping
    the entire day — e.g. if now is 8pm and the only gap starts at 3pm,
    the slot is advanced to 8pm (if the gap still fits).

    Returns slots in chronological order. An empty list means the day is
    fully packed (or no windows exist, e.g. Saturday work task).
    """
    windows = get_valid_windows(
        target_date, task_type, user_tz, config,
        is_off_hours_allowed, is_workday_allowed,
    )
    if not windows:
        return []

    duration = timedelta(minutes=duration_minutes)
    buffer = timedelta(minutes=config.buffer_minutes)
    busy = merge_intervals(busy_intervals)

    all_slots: list[Interval] = []

    for win_start, win_end in windows:
        # Find the earliest cursor position for this window, accounting for
        # any busy event that ends within `buffer` before win_start.
        cursor = win_start
        for bs, be in busy:
            if be <= win_start and be > win_start - buffer:
                # Event ends just before the window; buffer pushes our start right
                required = be + buffer
                if required > cursor:
                    cursor = required
            # Events ending after win_start are handled in the main loop below

        # Advance cursor to min_start if we're running the scheduler in real
        # time — this prevents returning stale slots from earlier in the day.
        if min_start is not None and min_start > cursor:
            cursor = min_start

        if cursor >= win_end:
            continue  # min_start is past the entire window

        # Walk through busy intervals, finding free gaps in the window
        for bs, be in busy:
            # Skip events entirely before our cursor
            if be <= cursor:
                continue
            # Stop if this event starts at or after window end
            if bs >= win_end:
                break

            # There is a free gap between cursor and bs (clipped to window)
            gap_end = min(bs, win_end)
            if gap_end > cursor:
                slot_end = cursor + duration
                if slot_end <= gap_end:
                    all_slots.append((cursor, slot_end))

            # Advance cursor past this busy event + required buffer
            new_cursor = be + buffer
            cursor = max(cursor, new_cursor)

            if cursor >= win_end:
                break

        # Handle the remaining gap after the last busy event (or entire window)
        if cursor < win_end:
            slot_end = cursor + duration
            if slot_end <= win_end:
                all_slots.append((cursor, slot_end))

    return all_slots


def split_into_blocks(
    duration_minutes: int,
    config: SlotFinderConfig,
) -> list[int]:
    """
    Split a task duration into schedulable block sizes following CLAUDE.md rules:
      - Max single block: max_block_minutes (default 120)
      - Min split block: min_block_minutes (default 60)
      - Tasks over max_block_minutes are split into multiple sessions

    Returns a list of block durations in minutes.

    Examples:
      90  min → [90]         (fits in one block)
      120 min → [120]        (exactly one max block)
      150 min → [90, 60]     (split; second block at min size)
      180 min → [120, 60]    (max + min)
      240 min → [120, 120]   (two max blocks)
    """
    if duration_minutes <= config.max_block_minutes:
        return [duration_minutes]

    blocks: list[int] = []
    remaining = duration_minutes
    while remaining > 0:
        if remaining <= config.max_block_minutes:
            # Last block
            if remaining < config.min_block_minutes and blocks:
                # Merge with previous block rather than creating a sub-minimum block
                blocks[-1] += remaining
            else:
                blocks.append(remaining)
            break
        blocks.append(config.max_block_minutes)
        remaining -= config.max_block_minutes

    return blocks
