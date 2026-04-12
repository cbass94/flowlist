"""
Development seed script.
Populates the database with 1 mock user, 10 sample tasks in various states,
calendar blocks for scheduled tasks, and AI estimation log entries.

Run inside the backend container:
    docker compose exec backend python scripts/seed.py
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root or scripts/ dir
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.ai_estimation_log import AIEstimationLog
from app.models.calendar_block import CalendarBlock
from app.models.scheduling_run_log import ScheduleTrigger, SchedulingRunLog
from app.models.task import Task, TaskStatus, TaskType
from app.models.user import User

NOW = datetime.now(tz=timezone.utc)


def days(n: int) -> timedelta:
    return timedelta(days=n)


def hours(n: float) -> timedelta:
    return timedelta(hours=n)


async def seed(session: AsyncSession) -> None:
    # ── User ──────────────────────────────────────────────────────────────────
    # Prefer the first real (non-dev) user so seed tasks appear under the
    # account that is actually logged in. Fall back to creating a dev stub.
    from sqlalchemy import select
    result = await session.execute(
        select(User).order_by(User.id).limit(1)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email="dev@example.com",
            display_name="Dev User",
            timezone="America/Chicago",
            work_google_id="work-google-id-dev",
            work_access_token="FAKE_WORK_ACCESS_TOKEN",
            work_refresh_token="FAKE_WORK_REFRESH_TOKEN",
            work_token_expiry=NOW + days(1),
        )
        session.add(user)
        await session.flush()
    else:
        print(f"  Seeding tasks for existing user id={user.id} ({user.email})")

    # ── Tasks ─────────────────────────────────────────────────────────────────
    # 1 — Backlog, work, high priority
    t1 = Task(
        user_id=user.id,
        title="Prepare Q2 board deck",
        type=TaskType.work,
        priority=1,
        status=TaskStatus.backlog,
        estimated_duration_minutes=90,
        optional_user_estimate="~2 hours",
        optional_deadline=NOW + days(7),
    )

    # 2 — Backlog, work
    t2 = Task(
        user_id=user.id,
        title="Review and sign investor term sheet",
        type=TaskType.work,
        priority=2,
        status=TaskStatus.backlog,
        estimated_duration_minutes=60,
    )

    # 3 — Scheduled, work, has calendar blocks
    t3 = Task(
        user_id=user.id,
        title="Draft hiring plan for engineering team",
        type=TaskType.work,
        priority=3,
        status=TaskStatus.scheduled,
        estimated_duration_minutes=120,
        last_scheduled_at=NOW - hours(2),
    )

    # 4 — Scheduled, personal
    t4 = Task(
        user_id=user.id,
        title="Research and book summer vacation flights",
        type=TaskType.personal,
        priority=4,
        status=TaskStatus.scheduled,
        estimated_duration_minutes=60,
        is_workday_allowed=True,
        last_scheduled_at=NOW - hours(1),
    )

    # 5 — Tentatively Done, work (block's end time just passed)
    t5 = Task(
        user_id=user.id,
        title="Write onboarding doc for new sales hire",
        type=TaskType.work,
        priority=5,
        status=TaskStatus.tentatively_done,
        estimated_duration_minutes=90,
        last_scheduled_at=NOW - days(1),
    )

    # 6 — Done, work, with actual duration
    t6 = Task(
        user_id=user.id,
        title="Set up Stripe billing integration",
        type=TaskType.work,
        priority=6,
        status=TaskStatus.done,
        estimated_duration_minutes=120,
        actual_duration_minutes=95,
        completed_at=NOW - days(2),
        created_at=NOW - days(5),
    )

    # 7 — Delegated, work
    t7 = Task(
        user_id=user.id,
        title="Handle payroll tax filing with accountant",
        type=TaskType.work,
        priority=7,
        status=TaskStatus.delegated,
        notes="Handed off to Jane (finance)",
    )

    # 8 — Backlog, personal, with deadline
    t8 = Task(
        user_id=user.id,
        title="Buy birthday present for mom",
        type=TaskType.personal,
        priority=8,
        status=TaskStatus.backlog,
        estimated_duration_minutes=30,
        optional_deadline=NOW + days(5),
    )

    # 9 — Backlog, work, old task → procrastination candidate
    t9 = Task(
        user_id=user.id,
        title="Migrate legacy reporting dashboard to new data warehouse",
        type=TaskType.work,
        priority=9,
        status=TaskStatus.backlog,
        estimated_duration_minutes=120,
        procrastination_flag=True,
        created_at=NOW - days(20),  # older than watchdog threshold
        notes="Been on the list forever. Actually just punt to Q3.",
    )

    # 10 — Backlog, work, split task (Part 2 of t3 conceptually)
    t10 = Task(
        user_id=user.id,
        title="Draft hiring plan for engineering team - Part 2",
        type=TaskType.work,
        priority=10,
        status=TaskStatus.backlog,
        estimated_duration_minutes=60,
        optional_user_estimate="1 hr",
    )

    for task in [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10]:
        session.add(task)
    await session.flush()

    # Link t10 as continuation of t3
    t10.part_of_task_id = t3.id
    await session.flush()

    # ── Calendar blocks for scheduled/tentatively-done tasks ──────────────────
    # t3 — tomorrow 10am–12pm (work calendar)
    tomorrow_10am = (NOW + days(1)).replace(hour=10, minute=0, second=0, microsecond=0)
    cb1 = CalendarBlock(
        task_id=t3.id,
        google_event_id="google_evt_abc123",
        calendar_id=settings.work_calendar_id,
        account="work",
        start_at=tomorrow_10am,
        end_at=tomorrow_10am + hours(2),
    )

    # t4 — day after tomorrow 2pm–3pm (personal calendar, scheduled during work hours)
    dat_2pm = (NOW + days(2)).replace(hour=14, minute=0, second=0, microsecond=0)
    cb2 = CalendarBlock(
        task_id=t4.id,
        google_event_id="google_evt_def456",
        calendar_id=settings.personal_calendar_id,
        account="personal",
        start_at=dat_2pm,
        end_at=dat_2pm + hours(1),
    )

    # t5 — block that already ended (triggers tentatively_done state)
    yesterday_3pm = (NOW - days(1)).replace(hour=15, minute=0, second=0, microsecond=0)
    cb3 = CalendarBlock(
        task_id=t5.id,
        google_event_id="google_evt_ghi789",
        calendar_id=settings.work_calendar_id,
        account="work",
        start_at=yesterday_3pm,
        end_at=yesterday_3pm + hours(1.5),
    )

    # t6 — deleted block (task is done; block was cleaned up)
    five_days_ago_9am = (NOW - days(5)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    cb4 = CalendarBlock(
        task_id=t6.id,
        google_event_id="google_evt_jkl012",
        calendar_id=settings.work_calendar_id,
        account="work",
        start_at=five_days_ago_9am,
        end_at=five_days_ago_9am + hours(2),
        is_deleted=True,
        deleted_at=NOW - days(2),
    )

    for block in [cb1, cb2, cb3, cb4]:
        session.add(block)
    await session.flush()

    # ── AI estimation log entries ─────────────────────────────────────────────
    # Entry for t6 (done task — has both estimated and actual)
    log1 = AIEstimationLog(
        task_id=t6.id,
        task_type="work",
        task_title_snapshot="Set up Stripe billing integration",
        keywords=["stripe", "billing", "integration", "api", "payment"],
        estimated_minutes=120,
        actual_minutes=95,
        error_minutes=-25,
        model_used=settings.anthropic_model,
        created_at=NOW - days(5),
    )

    # Entry for t3 (scheduled — actual not yet known)
    log2 = AIEstimationLog(
        task_id=t3.id,
        task_type="work",
        task_title_snapshot="Draft hiring plan for engineering team",
        keywords=["hiring", "plan", "engineering", "recruitment", "headcount"],
        estimated_minutes=120,
        model_used=settings.anthropic_model,
        created_at=NOW - hours(3),
    )

    # Entry for t5 (tentatively done — actual not yet filled)
    log3 = AIEstimationLog(
        task_id=t5.id,
        task_type="work",
        task_title_snapshot="Write onboarding doc for new sales hire",
        keywords=["onboarding", "documentation", "sales", "writing"],
        estimated_minutes=90,
        model_used=settings.anthropic_model,
        created_at=NOW - days(2),
    )

    for log in [log1, log2, log3]:
        session.add(log)

    # ── Scheduling run log ────────────────────────────────────────────────────
    run1 = SchedulingRunLog(
        triggered_at=NOW - hours(3),
        completed_at=NOW - hours(3) + timedelta(seconds=4),
        trigger_reason=ScheduleTrigger.task_added,
        triggered_by_task_id=t3.id,
        tasks_affected=3,
        blocks_deleted=0,
        blocks_created=2,
        duration_ms=3812,
    )
    session.add(run1)

    await session.flush()
    print(f"Seed complete.")
    print(f"  User id={user.id}  email={user.email}")
    print(f"  Tasks created: 10")
    print(f"  Calendar blocks: 4 (3 active, 1 deleted)")
    print(f"  AI estimation log entries: 3")
    print(f"  Scheduling run log entries: 1")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
