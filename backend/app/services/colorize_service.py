"""
Calendar color-coding orchestrator (I/O).

Ties together the pure logic (app.services.colorize), the AI classifier
(ai_service.classify_events), Google Calendar patches
(calendar_service.patch_event_color), and two tables — event_colors (what
FlowList did to each event) and bucket_overrides (what the user wants for a
class of events) — to color the user's upcoming events by productivity bucket.

Design notes:
  - User overrides are resolved before the AI, so a corrected event is never
    re-classified and can never drift back to the bucket the user rejected.
  - Only events with a new/changed content signature are sent to Claude; the
    rest reuse their cached bucket. In steady state a run makes zero AI calls.
  - Recent corrections are fed into the prompt, so events the user has not seen
    yet are more likely to land in the right bucket first time.
  - A manual recolor in Google Calendar is read back as intent where possible
    (colorize.reverse_bucket) and recorded as an override — "adopt". Only a
    color that maps to no bucket still causes FlowList to cede.
  - On AI failure, classify_events returns None and nothing is recolored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories import bucket_override_repo, calendar_block_repo, event_color_repo
from app.services import ai_service, calendar_service, colorize

log = logging.getLogger(__name__)

_LOOKAHEAD_DAYS = 14


def _adopt_scope(candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
    """
    Where to record a color the user chose by hand.

    Uses the most specific key the event offers — the same precedence order
    resolution uses — so adopting never creates a rule broader than the thing
    the user actually recolored.
    """
    return candidates[0] if candidates else None


async def _load_overrides(db: AsyncSession, user_id: int) -> dict[tuple[str, str], str]:
    rows = await bucket_override_repo.get_by_user(db, user_id)
    return {(r.scope, r.match_key): r.bucket for r in rows}


async def colorize_user(db: AsyncSession, user: User) -> int:
    """
    Classify and color the user's timed events for the next ~14 days.
    Returns the number of events (re)colored. No-op if colorize_enabled is off.
    """
    if not user.colorize_enabled:
        return 0

    now = datetime.now(tz=timezone.utc)
    window_end = now + timedelta(days=_LOOKAHEAD_DAYS)

    # Calendars to scan / write to (work account can read both).
    work_cal = user.work_calendar_id or settings.work_calendar_id
    personal_cal = user.personal_calendar_id or settings.personal_calendar_id
    calendars: list[tuple[str, Literal["work", "personal"]]] = [(work_cal, "work")]
    if personal_cal and personal_cal != work_cal:
        personal_account: Literal["work", "personal"] = (
            "personal" if user.personal_google_id else "work"
        )
        calendars.append((personal_cal, personal_account))

    all_events: list[dict] = []
    for cal_id, create_account in calendars:
        events = await calendar_service.get_events_with_attendees(
            user, db, cal_id, "work", now, window_end
        )
        for ev in events:
            ev["_calendar_id"] = cal_id
            ev["_create_account"] = create_account
            all_events.append(ev)

    self_emails = user.synthesis_self_email_set
    color_map = user.bucket_color_map

    records = {r.google_event_id: r for r in await event_color_repo.get_by_user(db, user.id)}
    seen_ids: set[str] = {ev["id"] for ev in all_events if ev.get("id")}

    # Eligible events + their signatures.
    eligible: list[dict] = [ev for ev in all_events if ev.get("id") and colorize.is_colorable(ev, self_emails)]
    sigs = {ev["id"]: colorize.content_signature(ev) for ev in eligible}

    # Which of these events are a task's scheduled blocks? A per-task override
    # has to reach them, and blocks are recreated with new IDs on every
    # reschedule, so this mapping is rebuilt each run rather than stored.
    task_ids = await calendar_block_repo.get_task_ids_by_event_ids(
        db, user.id, [ev["id"] for ev in eligible]
    )
    overrides = await _load_overrides(db, user.id)
    candidates = {
        ev["id"]: colorize.override_key_candidates(ev, task_ids.get(ev["id"]))
        for ev in eligible
    }

    # Which events need a fresh classification? Not ones the user has already
    # ruled on (an override, or a color we ceded), and not ones whose content is
    # unchanged since we last classified them.
    to_classify: list[dict] = []
    for ev in eligible:
        eid = ev["id"]
        if colorize.resolve_override(candidates[eid], overrides) is not None:
            continue
        rec = records.get(eid)
        if rec is not None and rec.is_user_overridden:
            continue
        if rec is None or rec.content_signature != sigs[eid]:
            to_classify.append(ev)

    buckets_by_id: dict[str, str] = {}
    if to_classify:
        corrections = [
            {"summary": r.example_summary, "was": r.was_bucket, "bucket": r.bucket}
            for r in await bucket_override_repo.recent_for_prompt(db, user.id)
        ]
        results = await ai_service.classify_events(to_classify, corrections)
        for ev, bucket in zip(to_classify, results):
            if bucket is not None:
                buckets_by_id[ev["id"]] = bucket

    colored = 0
    adopted = 0
    for ev in eligible:
        eid = ev["id"]
        rec = records.get(eid)

        # Resolved inside the loop, so an override adopted from one instance of a
        # recurring meeting applies to its remaining instances in this same run
        # rather than waiting for the next one.
        resolved = colorize.resolve_override(candidates[eid], overrides)
        if resolved is not None:
            bucket = resolved[0]
        else:
            bucket = buckets_by_id.get(eid) or (rec.bucket if rec is not None else None)
        desired_color = color_map.get(bucket) if bucket else None

        adoptable_bucket = colorize.reverse_bucket(ev.get("color_id"), color_map)

        action = colorize.decide_action(
            ev.get("color_id"),
            has_record=rec is not None,
            record_applied_color=rec.applied_color_id if rec is not None else None,
            record_overridden=rec.is_user_overridden if rec is not None else False,
            desired_color=desired_color,
            adoptable=adoptable_bucket is not None,
        )

        if action == "skip":
            # Refresh the cached signature if content changed but the bucket
            # didn't, so we don't re-classify this event every run.
            if (
                rec is not None
                and not rec.is_user_overridden
                and bucket is not None
                and rec.content_signature != sigs[eid]
            ):
                await event_color_repo.upsert(
                    db,
                    user_id=user.id,
                    calendar_id=ev["_calendar_id"],
                    google_event_id=eid,
                    bucket=bucket,
                    applied_color_id=rec.applied_color_id,
                    content_signature=sigs[eid],
                )
                await db.commit()
            continue

        if action == "adopt":
            # The user painted this event a color that means something. Record it
            # as a durable rule so every matching event follows, and hand the
            # event back to normal management — their intent is now explicit, so
            # there is nothing left to cede.
            target = _adopt_scope(candidates[eid])
            if target is None:
                continue
            scope, match_key = target
            await bucket_override_repo.upsert(
                db,
                user_id=user.id,
                scope=scope,
                match_key=match_key,
                bucket=adoptable_bucket,
                was_bucket=rec.bucket if rec is not None else None,
                example_summary=(ev.get("summary") or "").strip()[:512] or None,
                source="gcal",
            )
            overrides[(scope, match_key)] = adoptable_bucket
            await event_color_repo.upsert(
                db,
                user_id=user.id,
                calendar_id=ev["_calendar_id"],
                google_event_id=eid,
                bucket=adoptable_bucket,
                applied_color_id=ev.get("color_id") or "",
                content_signature=sigs[eid],
                is_user_overridden=False,
            )
            await db.commit()
            adopted += 1
            log.info(
                "colorize_user: adopted %s override %r -> %s (user=%d)",
                scope, match_key, adoptable_bucket, user.id,
            )
            continue

        if action == "cede":
            if rec is not None:
                await event_color_repo.mark_overridden(db, rec)
            else:
                # Pre-existing manual color: remember it so we stop reconsidering.
                await event_color_repo.upsert(
                    db,
                    user_id=user.id,
                    calendar_id=ev["_calendar_id"],
                    google_event_id=eid,
                    bucket=bucket or "necessary",
                    applied_color_id=ev.get("color_id") or "",
                    content_signature=sigs[eid],
                    is_user_overridden=True,
                )
            await db.commit()
            continue

        # apply / update — need a classification to proceed
        if not bucket or not desired_color:
            continue
        try:
            await calendar_service.patch_event_color(
                user, db, ev["_calendar_id"], ev["_create_account"], eid, desired_color,
            )
        except Exception as exc:
            log.warning("colorize_user: patch failed for event %s: %s", eid, exc)
            continue

        await event_color_repo.upsert(
            db,
            user_id=user.id,
            calendar_id=ev["_calendar_id"],
            google_event_id=eid,
            bucket=bucket,
            applied_color_id=desired_color,
            content_signature=sigs[eid],
        )
        await db.commit()
        colored += 1

    pruned = await event_color_repo.prune(db, user.id, seen_ids)
    if pruned:
        await db.commit()

    log.info(
        "colorize_user: user=%d eligible=%d classified=%d colored=%d adopted=%d pruned=%d",
        user.id, len(eligible), len(to_classify), colored, adopted, pruned,
    )
    return colored
