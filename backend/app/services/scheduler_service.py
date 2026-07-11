"""
Scheduling engine — the brain of FlowList.

Architecture:
  schedule_all_tasks()      Orchestrates a full or windowed reschedule run.
                            Deletes future FlowList blocks, re-scans calendars,
                            assigns slots in priority order, creates GCal events.

  _clear_future_blocks()    Soft-deletes DB rows + deletes GCal events for the
                            reschedule window. Collects a deletion count for the run log.

  _assign_slots()           Greedy day-scanner: respects daily caps (2 work + 2 personal
                            per day), splits tasks >2 h, schedules all sessions.

  _rollback_created_blocks() Best-effort reversal of GCal events created before a failure.

Scheduling rules (from CLAUDE.md):
  - Work tasks: Mon–Fri 8am–5pm; personal: outside work hours
  - Hard limits: 7am–10pm any day
  - 30-min pre-buffer required before every auto-block
  - Max block: 2 h; min split block: 1 h
  - Tasks >2 h are split into 1–2 h sessions scheduled in priority order
  - Daily cap: 2 work blocks + 2 personal blocks per day
  - Full reschedule: all future blocks; windowed: next N days only

Trigger model:
  - task_added / task_deleted / task_updated → full reschedule
  - priority_change → windowed reschedule (72 h, debounced)
  - manual / startup → full reschedule
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.repositories import calendar_block_repo, scheduling_log_repo, task_repo
from app.services import calendar_service, colorize_service, synthesis
from app.services.slot_finder import SlotFinderConfig, merge_intervals, split_into_blocks

log = logging.getLogger(__name__)

# Maximum auto-blocks scheduled per type per day
_DAILY_WORK_CAP = 2
_DAILY_PERSONAL_CAP = 2

# How many future days to scan before giving up on placing a block
_MAX_SCAN_DAYS = 60

# How far ahead a full reschedule looks for meetings needing synthesis blocks.
# Meetings further out are too volatile to pre-book against.
_SYNTHESIS_LOOKAHEAD_DAYS = 14

# Triggers that only reschedule the next 72 hours instead of all future blocks
_WINDOWED_TRIGGERS = {ScheduleTrigger.priority_change}
_WINDOW_HOURS = 72


# ── Public API ────────────────────────────────────────────────────────────────


async def schedule_all_tasks(
    db: AsyncSession,
    user: User,
    trigger: ScheduleTrigger,
    triggered_by_task_id: int | None = None,
) -> None:
    """
    Main scheduling entry point. Fetches all active tasks, clears future FlowList
    calendar blocks within the reschedule window, then re-assigns time slots in
    priority order, creating Google Calendar events.

    Uses a scheduling run log to record what happened (including crashes — they
    show up as rows with null completed_at).

    Args:
        db:                  Active async DB session (caller manages lifecycle).
        user:                The User ORM object (with tokens loaded).
        trigger:             Why the reschedule was triggered.
        triggered_by_task_id: The task that caused it, if applicable.
    """
    started_at = time.monotonic()

    # Determine reschedule window
    now = datetime.now(tz=timezone.utc)
    if trigger in _WINDOWED_TRIGGERS:
        horizon = now + timedelta(hours=_WINDOW_HOURS)
    else:
        horizon = None  # None = all future blocks

    log.info(
        "schedule_all_tasks: user=%d trigger=%s horizon=%s",
        user.id,
        trigger.value,
        horizon.isoformat() if horizon else "full",
    )

    # Start a run log entry immediately so crashes are visible
    run = await scheduling_log_repo.start_run(
        db, trigger_reason=trigger, triggered_by_task_id=triggered_by_task_id
    )
    await db.commit()
    run_id = run.id

    blocks_deleted = 0
    blocks_created = 0
    tasks_scheduled: set[int] = set()
    # (google_event_id, calendar_id, account) for rollback
    created_events: list[tuple[str, str, str]] = []

    try:
        # ── Step 1: gather tasks ─────────────────────────────────────────────
        active_tasks = await task_repo.get_all_by_priority(
            db,
            user.id,
            exclude_statuses=[TaskStatus.done, TaskStatus.delegated],
        )

        schedulable = [
            t for t in active_tasks
            if t.estimated_duration_minutes and t.estimated_duration_minutes > 0
        ]

        if not schedulable:
            log.info("schedule_all_tasks: no schedulable tasks for user %d", user.id)
            await scheduling_log_repo.complete_run(
                db, run_id,
                tasks_affected=0, blocks_deleted=0, blocks_created=0,
                duration_ms=int((time.monotonic() - started_at) * 1000),
            )
            await db.commit()
            return

        # ── Step 2: clear future FlowList task blocks in window ─────────────
        blocks_to_delete = await _clear_future_blocks(db, user, now, horizon)
        blocks_deleted = len(blocks_to_delete)
        # Persist the clear before syncing synthesis, so the synthesis error
        # handler's rollback can never discard these (already-executed) deletes.
        await db.commit()

        # ── Step 2b: sync synthesis blocks after multi-person meetings ──────
        # Runs before slot assignment so synthesis blocks show up as busy in the
        # freebusy scan and task blocks flow around them. Isolated so a calendar
        # hiccup here never breaks task scheduling.
        try:
            await _sync_synthesis_blocks(db, user, now, horizon)
        except Exception as exc:
            log.warning(
                "schedule_all_tasks: synthesis sync failed for user %d: %s",
                user.id, exc,
            )
            await db.rollback()

        # ── Step 3: assign slots ─────────────────────────────────────────────
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

        new_blocks, tasks_scheduled, created_events = await _assign_slots(
            db=db,
            user=user,
            tasks=schedulable,
            scan_from=now,
            horizon=horizon,
            config=config,
        )
        blocks_created = new_blocks

        # ── Step 3b: color-code the calendar (opt-in) ───────────────────────
        # Runs after blocks are created so new task/synthesis blocks get colored
        # in the same pass. Isolated so a coloring failure never breaks the run.
        try:
            await colorize_service.colorize_user(db, user)
        except Exception as exc:
            log.warning(
                "schedule_all_tasks: colorize failed for user %d: %s", user.id, exc
            )
            await db.rollback()

        # ── Step 4: complete run log ─────────────────────────────────────────
        duration_ms = int((time.monotonic() - started_at) * 1000)
        await scheduling_log_repo.complete_run(
            db, run_id,
            tasks_affected=len(tasks_scheduled),
            blocks_deleted=blocks_deleted,
            blocks_created=blocks_created,
            duration_ms=duration_ms,
        )
        await db.commit()
        log.info(
            "schedule_all_tasks: done user=%d deleted=%d created=%d tasks=%d ms=%d",
            user.id, blocks_deleted, blocks_created, len(tasks_scheduled), duration_ms,
        )

    except Exception as exc:
        log.exception("schedule_all_tasks: failed for user %d: %s", user.id, exc)

        # Best-effort rollback of GCal events we created before the error
        if created_events:
            await _rollback_created_blocks(db, user, created_events)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        try:
            await db.rollback()
            await scheduling_log_repo.complete_run(
                db, run_id,
                tasks_affected=len(tasks_scheduled),
                blocks_deleted=blocks_deleted,
                blocks_created=0,
                duration_ms=duration_ms,
                error=str(exc)[:2000],
            )
            await db.commit()
        except Exception:
            log.exception("schedule_all_tasks: also failed to write error log")


# ── Internal helpers ──────────────────────────────────────────────────────────


async def _clear_future_blocks(
    db: AsyncSession,
    user: User,
    after: datetime,
    horizon: datetime | None,
) -> list[tuple[str, str, str]]:
    """
    Delete all future FlowList calendar blocks from Google Calendar and
    soft-delete them from the DB.

    Returns the list of (google_event_id, calendar_id, account) tuples that
    were processed (for logging / rollback awareness).
    """
    # Fetch blocks to delete from DB
    if horizon is not None:
        future_blocks = await calendar_block_repo.get_active_blocks_in_range(
            db, start=after, end=horizon
        )
    else:
        future_blocks = await calendar_block_repo.get_active_future_blocks(
            db, after=after
        )
    # Filter to this user's tasks
    task_ids = {t.id for t in await task_repo.get_all_by_priority(db, user.id)}
    future_blocks = [b for b in future_blocks if b.task_id in task_ids]

    if not future_blocks:
        return []

    deleted: list[tuple[str, str, str]] = []

    for block in future_blocks:
        try:
            await calendar_service.delete_calendar_block(
                user=user,
                db=db,
                calendar_id=block.calendar_id,
                account=block.account,
                google_event_id=block.google_event_id,
            )
            deleted.append((block.google_event_id, block.calendar_id, block.account))
        except Exception as exc:
            # Log but continue — stale events are better than a failed reschedule
            log.warning(
                "_clear_future_blocks: could not delete event %s: %s",
                block.google_event_id, exc,
            )

    return deleted


async def _sync_synthesis_blocks(
    db: AsyncSession,
    user: User,
    scan_from: datetime,
    horizon: datetime | None,
) -> int:
    """
    Reconcile "Synthesis time" blocks against the user's current meetings.

    For every meeting in the window that includes someone other than the user
    (and isn't declined/all-day/cancelled), ensure a 15-min synthesis block sits
    immediately after it — as long as it fits inside the hard day limits and the
    slot isn't occupied by a non-FlowList event. Reconciliation is idempotent:
    unchanged blocks are left alone, moved meetings get their block moved,
    meetings that no longer qualify get their block removed.

    Returns the number of synthesis blocks created (for logging).
    """
    window_end = (
        horizon if horizon is not None
        else scan_from + timedelta(days=_SYNTHESIS_LOOKAHEAD_DAYS)
    )

    # Existing synthesis blocks in this window, keyed by their source meeting.
    existing = await calendar_block_repo.get_active_synthesis_blocks_in_range(
        db, user.id, scan_from, window_end
    )
    existing_by_source: dict[str, "calendar_block_repo.CalendarBlock"] = {
        b.source_google_event_id: b for b in existing if b.source_google_event_id
    }

    # Feature toggle off → tear down any existing synthesis blocks and stop.
    if not user.synthesis_enabled:
        for block in existing_by_source.values():
            await _delete_synthesis_block(db, user, block)
        return 0

    # Which calendars to scan / write to. Work account can read both calendars.
    work_cal = user.work_calendar_id or settings.work_calendar_id
    personal_cal = user.personal_calendar_id or settings.personal_calendar_id
    calendars: list[tuple[str, Literal["work", "personal"]]] = [(work_cal, "work")]
    if personal_cal and personal_cal != work_cal:
        personal_account: Literal["work", "personal"] = (
            "personal" if user.personal_google_id else "work"
        )
        calendars.append((personal_cal, personal_account))

    # Gather events across all calendars, tagging each with where a synthesis
    # block for it would be written.
    all_events: list[dict] = []
    for cal_id, create_account in calendars:
        events = await calendar_service.get_events_with_attendees(
            user, db, cal_id, "work", scan_from, window_end
        )
        for ev in events:
            ev["_calendar_id"] = cal_id
            ev["_create_account"] = create_account
            all_events.append(ev)

    # External busy = non-FlowList, timed, non-cancelled, non-transparent events
    # across BOTH calendars. FlowList task blocks are deliberately excluded so
    # they get shuffled out of the way rather than blocking a synthesis buffer.
    external_busy = merge_intervals([
        (ev["start_dt"], ev["end_dt"])
        for ev in all_events
        if not ev["is_flowlist"]
        and not ev["is_all_day"]
        and ev["start_dt"] is not None
        and ev["end_dt"] is not None
        and ev["status"] != "cancelled"
        and ev.get("transparency") != "transparent"
    ])

    self_emails = user.synthesis_self_email_set
    duration = user.synthesis_duration_minutes or 15

    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        user_tz = ZoneInfo(user.timezone or "UTC")
    except (ZoneInfoNotFoundError, KeyError):
        user_tz = ZoneInfo("UTC")

    # Desired synthesis blocks: source_event_id → (start, end, calendar_id, account)
    desired: dict[str, tuple[datetime, datetime, str, str]] = {}
    for ev in all_events:
        source_id = ev["id"]
        if not source_id:
            continue
        if not synthesis.is_multiperson_meeting(ev, self_emails):
            continue
        end_dt = ev["end_dt"]
        if end_dt is None or end_dt <= scan_from:
            continue  # only place synthesis after meetings that end in the future
        win = synthesis.compute_synthesis_window(
            end_dt, duration, user.hard_start_hour, user.hard_end_hour,
            external_busy, user_tz,
        )
        if win is None:
            continue
        desired[source_id] = (win[0], win[1], ev["_calendar_id"], ev["_create_account"])

    created = 0

    # Create new blocks / move blocks whose meeting shifted.
    for source_id, (start_at, end_at, cal_id, account) in desired.items():
        block = existing_by_source.get(source_id)
        if (
            block is not None
            and block.start_at == start_at
            and block.end_at == end_at
            and block.calendar_id == cal_id
        ):
            continue  # unchanged — leave the existing event alone
        if block is not None:
            await _delete_synthesis_block(db, user, block)
        await calendar_service.create_synthesis_block(
            user=user,
            db=db,
            calendar_id=cal_id,
            account=account,  # type: ignore[arg-type]
            start_time=start_at,
            end_time=end_at,
            source_google_event_id=source_id,
        )
        await db.commit()
        created += 1

    # Remove synthesis blocks whose meeting no longer qualifies (cancelled,
    # moved out of window, lost its other attendees, now conflicting, etc.).
    for source_id, block in existing_by_source.items():
        if source_id not in desired:
            await _delete_synthesis_block(db, user, block)

    if created or existing_by_source:
        log.info(
            "_sync_synthesis_blocks: user=%d created=%d existing=%d desired=%d",
            user.id, created, len(existing_by_source), len(desired),
        )
    return created


async def _delete_synthesis_block(db: AsyncSession, user: User, block) -> None:
    """Delete a synthesis block from GCal + soft-delete its row, then commit."""
    try:
        await calendar_service.delete_calendar_block(
            user=user,
            db=db,
            calendar_id=block.calendar_id,
            account=block.account,
            google_event_id=block.google_event_id,
        )
        await db.commit()
    except Exception as exc:
        log.warning(
            "_delete_synthesis_block: could not delete %s: %s",
            block.google_event_id, exc,
        )


async def _assign_slots(
    db: AsyncSession,
    user: User,
    tasks: list[Task],
    scan_from: datetime,
    horizon: datetime | None,
    config: SlotFinderConfig,
) -> tuple[int, set[int], list[tuple[str, str, str]]]:
    """
    Greedy scheduler: scan days from `scan_from` onward, filling the earliest
    available slot for each task block in priority order.

    Daily cap: 2 work blocks + 2 personal blocks per day.

    For split tasks (duration > max_block_minutes), all sessions are queued in
    order — the second session is scheduled right after the first, even if that
    means skipping to a later day.

    Returns:
        (blocks_created, set of task_ids that got at least one block, created_event_tuples)
    """
    # Build a queue of (task, block_duration_minutes) in priority order
    WorkItem = tuple[Task, int]
    queue: list[WorkItem] = []

    for task in tasks:
        blocks = split_into_blocks(task.estimated_duration_minutes, config)
        for block_mins in blocks:
            queue.append((task, block_mins))

    if not queue:
        return 0, set(), []

    # Daily cap tracker: {date: {"work": int, "personal": int}}
    daily_counts: dict[date, dict[str, int]] = defaultdict(lambda: {"work": 0, "personal": 0})

    # Also pre-populate counts from existing blocks NOT in our delete window
    # (non-FlowList events don't count toward our cap — only our own blocks do)
    # We'll simply not double-schedule into days that are already at cap from
    # blocks we didn't touch (blocks before `scan_from` or beyond `horizon`).

    blocks_created = 0
    tasks_scheduled: set[int] = set()
    created_events: list[tuple[str, str, str]] = []

    for task, duration_mins in queue:
        task_type = task.type.value  # "work" or "personal"
        cap = _DAILY_WORK_CAP if task_type == "work" else _DAILY_PERSONAL_CAP
        cap_key = task_type

        # Determine which calendar to use
        calendar_id = (
            (user.work_calendar_id or settings.work_calendar_id)
            if task_type == "work"
            else (user.personal_calendar_id or settings.personal_calendar_id)
        )
        account: Literal["work", "personal"] = (
            "work" if task_type == "work" else
            ("personal" if user.personal_google_id else "work")
        )

        # Scan days until we find a usable slot.
        # Use the user's local timezone for the starting date — using UTC here
        # would skip the current local day for users with negative UTC offsets
        # (e.g. America/Chicago UTC-5: after 7pm local = next UTC day).
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            _scan_tz = ZoneInfo(user.timezone or "UTC")
        except (ZoneInfoNotFoundError, KeyError):
            _scan_tz = ZoneInfo("UTC")
        scan_date = scan_from.astimezone(_scan_tz).date()
        log.debug(
            "_assign_slots: task %d scan_from=%s (UTC) → scan_date=%s (local tz=%s)",
            task.id, scan_from.isoformat(), scan_date, user.timezone,
        )
        placed = False

        for day_offset in range(_MAX_SCAN_DAYS):
            candidate_date = scan_date + timedelta(days=day_offset)

            # Respect horizon for windowed reschedules
            if horizon is not None:
                day_start_dt = datetime(
                    candidate_date.year, candidate_date.month, candidate_date.day,
                    0, 0, 0, tzinfo=timezone.utc,
                )
                if day_start_dt >= horizon:
                    break  # Outside window — stop scanning

            # Check daily cap
            if daily_counts[candidate_date][cap_key] >= cap:
                continue

            # Find free slots for this task on this day.
            # Pass scan_from as min_start on the first day so the slot finder
            # advances past already-elapsed times within each gap, rather than
            # returning an early-morning slot that is already in the past.
            min_start_for_day = scan_from if candidate_date == scan_date else None
            try:
                slots = await calendar_service.find_free_slots_for_task(
                    user=user,
                    db=db,
                    task=task,
                    target_date=candidate_date,
                    duration_minutes=duration_mins,
                    min_start=min_start_for_day,
                )
            except Exception as exc:
                log.warning(
                    "_assign_slots: slot lookup failed for task %d on %s: %s",
                    task.id, candidate_date, exc,
                )
                continue

            if not slots:
                continue

            start_time, end_time = slots[0]

            # Create the calendar event
            try:
                block = await calendar_service.create_calendar_block(
                    user=user,
                    db=db,
                    task=task,
                    calendar_id=calendar_id,
                    account=account,
                    start_time=start_time,
                    end_time=end_time,
                )
                # Update task status and last_scheduled_at
                await task_repo.update_fields(
                    db, task.id,
                    status=TaskStatus.scheduled,
                    last_scheduled_at=start_time,
                )
                await db.commit()
            except Exception as exc:
                log.warning(
                    "_assign_slots: failed to create block for task %d on %s: %s",
                    task.id, candidate_date, exc,
                )
                # Raise to trigger outer rollback
                raise

            daily_counts[candidate_date][cap_key] += 1
            blocks_created += 1
            tasks_scheduled.add(task.id)
            created_events.append(
                (block.google_event_id, calendar_id, account)
            )
            placed = True
            break

        if not placed:
            log.warning(
                "_assign_slots: could not place task %d (%s) within %d days",
                task.id, task.title[:40], _MAX_SCAN_DAYS,
            )

    return blocks_created, tasks_scheduled, created_events


async def _rollback_created_blocks(
    db: AsyncSession,
    user: User,
    created_events: list[tuple[str, str, str]],
) -> None:
    """
    Best-effort deletion of GCal events we created before a failure.
    Errors are logged but not re-raised — we do our best and move on.
    """
    log.info("_rollback_created_blocks: rolling back %d events", len(created_events))
    for google_event_id, calendar_id, account in created_events:
        try:
            await calendar_service.delete_calendar_block(
                user=user,
                db=db,
                calendar_id=calendar_id,
                account=account,
                google_event_id=google_event_id,
            )
        except Exception as exc:
            log.warning(
                "_rollback_created_blocks: could not delete %s: %s",
                google_event_id, exc,
            )
