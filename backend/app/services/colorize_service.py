"""
Calendar color-coding orchestrator (I/O).

Ties together the pure logic (app.services.colorize), the AI classifier
(ai_service.classify_events), Google Calendar patches
(calendar_service.patch_event_color), and the event_colors cache/ownership
table to color the user's upcoming events by productivity bucket.

Design notes:
  - Only events with a new/changed content signature are sent to Claude; the
    rest reuse their cached bucket. In steady state a run makes zero AI calls.
  - Manual color edits are respected via colorize.decide_action + the
    is_user_overridden flag — FlowList only manages colors it set itself.
  - On AI failure, classify_events returns None and nothing is recolored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories import event_color_repo
from app.services import ai_service, calendar_service, colorize

log = logging.getLogger(__name__)

_LOOKAHEAD_DAYS = 14


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

    # Which events need a fresh classification (new or content changed, and not
    # a ceded/user-owned event)?
    to_classify: list[dict] = []
    for ev in eligible:
        rec = records.get(ev["id"])
        if rec is not None and rec.is_user_overridden:
            continue
        if rec is None or rec.content_signature != sigs[ev["id"]]:
            to_classify.append(ev)

    buckets_by_id: dict[str, str] = {}
    if to_classify:
        results = await ai_service.classify_events(to_classify)
        for ev, bucket in zip(to_classify, results):
            if bucket is not None:
                buckets_by_id[ev["id"]] = bucket

    colored = 0
    for ev in eligible:
        eid = ev["id"]
        rec = records.get(eid)
        bucket = buckets_by_id.get(eid) or (rec.bucket if rec is not None else None)
        desired_color = color_map.get(bucket) if bucket else None

        action = colorize.decide_action(
            ev.get("color_id"),
            has_record=rec is not None,
            record_applied_color=rec.applied_color_id if rec is not None else None,
            record_overridden=rec.is_user_overridden if rec is not None else False,
            desired_color=desired_color,
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
        "colorize_user: user=%d eligible=%d classified=%d colored=%d pruned=%d",
        user.id, len(eligible), len(to_classify), colored, pruned,
    )
    return colored
