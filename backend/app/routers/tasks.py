"""
Tasks router — CRUD, priority reorder, and scheduling triggers.

Transaction management:
  get_db() owns the single per-request transaction (commit on success,
  rollback on exception). Routes must NOT call db.begin() — a transaction
  is already active when any query runs inside get_current_user.
"""

import logging
import uuid

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.task import TaskStatus
from app.models.user import User
from app.repositories import ai_log_repo, calendar_block_repo, task_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.task import (
    BlockDoneRequest,
    CompleteRequest,
    MoreWorkRequest,
    MoreWorkSuggestion,
    RescheduleAllOverdueResponse,
    ReorderRequest,
    TaskBlockInfo,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from app.services import ai_service, calendar_service
from app.services.auth_service import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


async def _task_read_with_next_start(db: AsyncSession, task: "Task") -> TaskRead:
    """Build a TaskRead with next_scheduled_start and blocks populated from calendar_blocks."""
    next_starts = await calendar_block_repo.get_earliest_start_by_task_ids(db, [task.id])
    blocks_map = await calendar_block_repo.get_active_blocks_by_task_ids(db, [task.id])
    blocks = [TaskBlockInfo.model_validate(b) for b in blocks_map.get(task.id, [])]
    return TaskRead.model_validate(task).model_copy(
        update={
            "next_scheduled_start": next_starts.get(task.id),
            "blocks": blocks,
        }
    )

_DEBOUNCE_KEY = "reschedule:token:{user_id}"
_TERMINAL_STATUSES = [TaskStatus.done, TaskStatus.delegated]
_RESCHEDULE_FIELDS = {"estimated_duration_minutes", "type", "is_off_hours_allowed", "is_workday_allowed", "no_weekends"}


def _parse_redis_url(url: str) -> RedisSettings:
    import re
    from urllib.parse import unquote
    rest = re.sub(r"^rediss?://", "", url.strip())
    m = re.match(
        r"^(?::(?P<password>[^@]*)@)?"
        r"(?P<host>[^:/]+)"
        r"(?::(?P<port>\d+))?"
        r"(?:/(?P<db>\d+))?",
        rest,
    )
    if not m:
        return RedisSettings()
    raw_password = m.group("password")
    return RedisSettings(
        host=m.group("host") or "localhost",
        port=int(m.group("port") or 6379),
        password=unquote(raw_password) if raw_password else None,
        database=int(m.group("db") or 0),
    )


async def _enqueue_reschedule(
    user_id: int,
    trigger: ScheduleTrigger,
    debounce: bool = False,
) -> None:
    try:
        redis_settings = _parse_redis_url(settings.redis_url)
        pool = await create_pool(redis_settings)
        token = f"{trigger.value}:{uuid.uuid4().hex}"
        if debounce:
            key = _DEBOUNCE_KEY.format(user_id=user_id)
            await pool.set(key, token, ex=10)
            await pool.enqueue_job("reschedule_all", user_id, token, _defer_by=2)
        else:
            await pool.enqueue_job("reschedule_all", user_id, token)
        await pool.aclose()
    except Exception:
        log.warning(
            "_enqueue_reschedule: failed for user %d trigger %s",
            user_id, trigger.value, exc_info=True,
        )


# ── CRUD ──────────────────────────────────────────────────────────────────────


@router.get("/", response_model=ApiResponse[list[TaskRead]], summary="List tasks")
async def list_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskRead]]:
    tasks = await task_repo.get_all_by_priority(
        db, current_user.id, exclude_statuses=_TERMINAL_STATUSES
    )
    task_ids = [t.id for t in tasks]
    next_starts = await calendar_block_repo.get_earliest_start_by_task_ids(db, task_ids)
    blocks_map = await calendar_block_repo.get_active_blocks_by_task_ids(db, task_ids)
    reads = [
        TaskRead.model_validate(t).model_copy(update={
            "next_scheduled_start": next_starts.get(t.id),
            "blocks": [TaskBlockInfo.model_validate(b) for b in blocks_map.get(t.id, [])],
        })
        for t in tasks
    ]
    return ok(reads, meta={"total": len(reads)})


@router.post("/", response_model=ApiResponse[TaskRead], status_code=201, summary="Create task")
async def create_task(
    body: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    # Always insert new tasks at the top of the backlog (priority 1),
    # shifting all existing active tasks down by 1.
    await task_repo.insert_at_top(db, current_user.id)
    priority = 1

    task = await task_repo.create(
        db,
        user_id=current_user.id,
        title=body.title,
        task_type=body.type,
        priority=priority,
        estimated_duration_minutes=body.estimated_duration_minutes,
        optional_user_estimate=body.optional_user_estimate,
        optional_deadline=body.optional_deadline,
        is_off_hours_allowed=body.is_off_hours_allowed,
        is_workday_allowed=body.is_workday_allowed,
        no_weekends=body.no_weekends,
        part_of_task_id=body.part_of_task_id,
        description=body.description,
    )

    if body.estimated_duration_minutes:
        await ai_log_repo.log_estimation(
            db,
            task_id=task.id,
            task_type=body.type.value,
            task_title_snapshot=body.title,
            estimated_minutes=body.estimated_duration_minutes,
            model_used=f"confidence:{body.ai_confidence or 'unknown'}",
            keywords=body.ai_keywords,
        )

    # Flush so task.id is populated; get_db commits at end of request
    await db.flush()

    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_added)
    return ok(await _task_read_with_next_start(db, task))


@router.patch("/reorder", response_model=ApiResponse[None], summary="Reorder task priorities")
async def reorder_tasks(
    body: ReorderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await task_repo.reorder(db, current_user.id, body.ordered_task_ids)
    await _enqueue_reschedule(
        current_user.id, ScheduleTrigger.priority_change, debounce=True
    )
    return ok(None)


@router.patch("/{task_id}", response_model=ApiResponse[TaskRead], summary="Update task")
async def update_task(
    task_id: int,
    body: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    updates = body.model_dump(exclude_unset=True)
    if updates:
        task = await task_repo.update_fields(db, task_id, **updates)

    changed_fields = set(updates.keys())
    if changed_fields & _RESCHEDULE_FIELDS:
        await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)

    # When description changes, patch the description of future GCal events (best-effort)
    if "description" in changed_fields and task is not None:
        try:
            await calendar_service.update_future_block_descriptions(current_user, db, task)
        except Exception:
            log.warning(
                "update_task: failed to patch GCal event descriptions for task %d",
                task_id, exc_info=True,
            )

    return ok(await _task_read_with_next_start(db, task))


@router.delete("/{task_id}", response_model=ApiResponse[None], summary="Delete task")
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    await calendar_block_repo.soft_delete_by_task(db, task_id)
    await task_repo.delete(db, task_id)
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_deleted)
    return ok(None)


@router.post("/{task_id}/complete", response_model=ApiResponse[TaskRead], summary="Complete task")
async def complete_task(
    task_id: int,
    body: CompleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    from datetime import datetime, timezone

    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Cancel all future calendar blocks for this task (past blocks stay as records)
    now = datetime.now(tz=timezone.utc)
    all_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    future_blocks = [b for b in all_blocks if b.start_at >= now]
    for block in future_blocks:
        try:
            await calendar_service.delete_calendar_block(
                current_user, db,
                calendar_id=block.calendar_id,
                account=block.account,  # type: ignore[arg-type]
                google_event_id=block.google_event_id,
            )
        except Exception:
            log.warning(
                "complete_task: failed to cancel GCal event %s for task %d",
                block.google_event_id, task_id, exc_info=True,
            )

    # Cancel all blocks and mark done for any continuation tasks (Part 2, etc.)
    continuation_tasks = await task_repo.get_continuation_tasks(db, task_id)
    for cont in continuation_tasks:
        if cont.status in _TERMINAL_STATUSES:
            continue
        cont_blocks = await calendar_block_repo.get_active_blocks_for_task(db, cont.id)
        for block in cont_blocks:
            try:
                await calendar_service.delete_calendar_block(
                    current_user, db,
                    calendar_id=block.calendar_id,
                    account=block.account,  # type: ignore[arg-type]
                    google_event_id=block.google_event_id,
                )
            except Exception:
                log.warning(
                    "complete_task: failed to cancel GCal event %s for continuation task %d",
                    block.google_event_id, cont.id, exc_info=True,
                )
        await task_repo.mark_complete(db, cont.id)

    task = await task_repo.mark_complete(
        db, task_id, actual_duration_minutes=body.actual_duration_minutes
    )
    if body.actual_duration_minutes:
        await ai_service.record_task_completion(
            db, task_id, body.actual_duration_minutes
        )

    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_deleted)
    return ok(await _task_read_with_next_start(db, task))


@router.post("/{task_id}/delegate", response_model=ApiResponse[TaskRead], summary="Delegate task")
async def delegate_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    # Cancel Google Calendar events for all active blocks (best-effort)
    active_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    for block in active_blocks:
        try:
            await calendar_service.delete_calendar_block(
                current_user, db,
                calendar_id=block.calendar_id,
                account=block.account,  # type: ignore[arg-type]
                google_event_id=block.google_event_id,
            )
        except Exception:
            # Log the failure but do NOT soft-delete the DB block — if the GCal
            # deletion failed, the block stays active so the next reschedule can
            # retry the GCal cancellation. Soft-deleting here would orphan the event.
            log.warning(
                "delegate_task: failed to cancel GCal event %s for task %d — "
                "block left active for retry on next reschedule",
                block.google_event_id, task_id, exc_info=True,
            )

    task = await task_repo.update_fields(
        db, task_id, status=TaskStatus.delegated, procrastination_flag=False
    )
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_deleted)
    return ok(await _task_read_with_next_start(db, task))


async def _get_overdue_tasks(db: AsyncSession, user_id: int) -> list:
    """Return scheduled/tentatively_done tasks that have at least one non-deleted block starting in the past."""
    from datetime import datetime, timezone
    from sqlalchemy import and_, exists, select
    from app.models.calendar_block import CalendarBlock
    from app.models.task import Task as TaskModel
    now = datetime.now(tz=timezone.utc)
    overdue_block_exists = exists().where(
        and_(
            CalendarBlock.task_id == TaskModel.id,
            CalendarBlock.is_deleted.is_(False),
            CalendarBlock.start_at <= now,
        )
    )
    result = await db.execute(
        select(TaskModel).where(
            TaskModel.user_id == user_id,
            TaskModel.status.in_([TaskStatus.scheduled, TaskStatus.tentatively_done]),
            overdue_block_exists,
        )
    )
    return list(result.scalars().all())


@router.post(
    "/reschedule-all-overdue",
    response_model=ApiResponse[RescheduleAllOverdueResponse],
    summary="Reschedule all overdue tasks in a single batch",
)
async def reschedule_all_overdue(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[RescheduleAllOverdueResponse]:
    overdue_tasks = await _get_overdue_tasks(db, current_user.id)
    if not overdue_tasks:
        return ok(RescheduleAllOverdueResponse(rescheduled_task_ids=[], task_count=0))

    for task in overdue_tasks:
        active_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task.id)
        for block in active_blocks:
            try:
                await calendar_service.delete_calendar_block(
                    current_user, db,
                    calendar_id=block.calendar_id,
                    account=block.account,  # type: ignore[arg-type]
                    google_event_id=block.google_event_id,
                )
            except Exception:
                log.warning(
                    "reschedule_all_overdue: failed to cancel GCal event %s for task %d — "
                    "block left active for retry on next reschedule",
                    block.google_event_id, task.id, exc_info=True,
                )

    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)
    return ok(RescheduleAllOverdueResponse(
        rescheduled_task_ids=[t.id for t in overdue_tasks],
        task_count=len(overdue_tasks),
    ))


@router.post("/{task_id}/reschedule-overdue", response_model=ApiResponse[TaskRead], summary="Reschedule an overdue task into the next available slot")
async def reschedule_overdue(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in (TaskStatus.scheduled, TaskStatus.tentatively_done):
        raise HTTPException(status_code=409, detail="Task is not in scheduled status")

    active_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    for block in active_blocks:
        try:
            await calendar_service.delete_calendar_block(
                current_user, db,
                calendar_id=block.calendar_id,
                account=block.account,  # type: ignore[arg-type]
                google_event_id=block.google_event_id,
            )
        except Exception:
            log.warning(
                "reschedule_overdue: failed to cancel GCal event %s for task %d — "
                "block left active for retry on next reschedule",
                block.google_event_id, task_id, exc_info=True,
            )

    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)
    return ok(await _task_read_with_next_start(db, task))


@router.get(
    "/{task_id}/more-work-suggestion",
    response_model=ApiResponse[MoreWorkSuggestion],
    summary="Get an AI-suggested additional duration for the more-work flow",
)
async def more_work_suggestion(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MoreWorkSuggestion]:
    from datetime import datetime, timezone
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    now = datetime.now(tz=timezone.utc)
    blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    past_minutes = sum(
        int((b.end_at - b.start_at).total_seconds() // 60)
        for b in blocks if b.start_at <= now
    )
    future_minutes = sum(
        int((b.end_at - b.start_at).total_seconds() // 60)
        for b in blocks if b.start_at > now
    )

    suggestion = await ai_service.suggest_more_work_minutes(
        title=task.title,
        task_type=task.type.value,
        original_estimate_minutes=task.estimated_duration_minutes,
        past_scheduled_minutes=past_minutes,
        future_scheduled_minutes=future_minutes,
    )

    return ok(MoreWorkSuggestion(
        suggested_additional_minutes=suggestion["minutes"],
        original_estimate_minutes=task.estimated_duration_minutes,
        scheduled_past_minutes=past_minutes,
        scheduled_future_minutes=future_minutes,
        ai_available=suggestion["ai_available"],
    ))


@router.post(
    "/{task_id}/more-work",
    response_model=ApiResponse[TaskRead],
    summary="Add more scheduled time to a task without disturbing past chunks",
)
async def more_work(
    task_id: int,
    body: MoreWorkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    """
    User confirmed they need more time on a task.
    - Past chunks are left untouched (no GCal change, no DB change).
    - Future chunks will be cleared and re-created by the scheduler.
    - estimated_duration_minutes is set so the scheduler produces
      (current future-scheduled minutes + additional_minutes) of new chunks.
    """
    from datetime import datetime, timezone
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    now = datetime.now(tz=timezone.utc)
    blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    future_minutes = sum(
        int((b.end_at - b.start_at).total_seconds() // 60)
        for b in blocks if b.start_at > now
    )

    # Scheduler clears future blocks and re-creates `estimated_duration_minutes`
    # worth of new chunks. So aim for: (existing future) + (additional).
    new_estimate = future_minutes + body.additional_minutes
    new_estimate = max(15, min(960, new_estimate))

    await task_repo.update_fields(db, task_id, estimated_duration_minutes=new_estimate)
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)

    refreshed = await task_repo.get_by_id(db, task_id)
    return ok(await _task_read_with_next_start(db, refreshed))


@router.post(
    "/{task_id}/blocks/{block_id}/done",
    response_model=ApiResponse[TaskRead],
    summary="Mark a single chunk as done and reschedule remaining work",
)
async def complete_block(
    task_id: int,
    block_id: int,
    body: BlockDoneRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    from datetime import datetime, timezone
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    all_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    blocks_sorted = sorted(all_blocks, key=lambda b: b.start_at)

    try:
        idx = next(i for i, b in enumerate(blocks_sorted) if b.id == block_id)
    except StopIteration:
        raise HTTPException(status_code=404, detail="Block not found")

    block = blocks_sorted[idx]
    now = datetime.now(tz=timezone.utc)

    # Keep past/current GCal event (it represents real work done); cancel future ones
    blocks_to_cancel = (
        blocks_sorted[idx + 1:]   # subsequent only — past block stays
        if block.start_at <= now
        else blocks_sorted[idx:]  # cancel this block too if it's still in the future
    )

    for b in blocks_to_cancel:
        try:
            await calendar_service.delete_calendar_block(
                current_user, db,
                calendar_id=b.calendar_id,
                account=b.account,  # type: ignore[arg-type]
                google_event_id=b.google_event_id,
            )
        except Exception:
            log.warning("complete_block: failed to cancel GCal event %s", b.google_event_id, exc_info=True)

    if body.confirmed_remaining_minutes == 0:
        await task_repo.update_fields(db, task_id, status=TaskStatus.done)
    else:
        await task_repo.update_fields(db, task_id, estimated_duration_minutes=body.confirmed_remaining_minutes)
        await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)

    refreshed = await task_repo.get_by_id(db, task_id)
    return ok(await _task_read_with_next_start(db, refreshed))


@router.post(
    "/{task_id}/blocks/{block_id}/reschedule",
    response_model=ApiResponse[TaskRead],
    summary="Reschedule a chunk and all subsequent chunks",
)
async def reschedule_block(
    task_id: int,
    block_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    all_blocks = await calendar_block_repo.get_active_blocks_for_task(db, task_id)
    blocks_sorted = sorted(all_blocks, key=lambda b: b.start_at)

    try:
        idx = next(i for i, b in enumerate(blocks_sorted) if b.id == block_id)
    except StopIteration:
        raise HTTPException(status_code=404, detail="Block not found")

    blocks_to_cancel = blocks_sorted[idx:]  # this block + all subsequent
    remaining = sum(
        int((b.end_at - b.start_at).total_seconds() // 60)
        for b in blocks_to_cancel
    )

    for b in blocks_to_cancel:
        try:
            await calendar_service.delete_calendar_block(
                current_user, db,
                calendar_id=b.calendar_id,
                account=b.account,  # type: ignore[arg-type]
                google_event_id=b.google_event_id,
            )
        except Exception:
            log.warning("reschedule_block: failed to cancel GCal event %s", b.google_event_id, exc_info=True)

    await task_repo.update_fields(db, task_id, estimated_duration_minutes=remaining)
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)

    refreshed = await task_repo.get_by_id(db, task_id)
    return ok(await _task_read_with_next_start(db, refreshed))


@router.delete(
    "/{task_id}/blocks/{block_id}",
    response_model=ApiResponse[TaskRead],
    summary="Delete a single scheduled calendar block from a task",
)
async def delete_task_block(
    task_id: int,
    block_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    """
    Delete a single calendar chunk (GCal event + DB soft-delete).
    Does not trigger a reschedule — the user is explicitly cleaning up.
    """
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    block = await calendar_block_repo.get_by_id(db, block_id)
    if block is None or block.task_id != task_id or block.is_deleted:
        raise HTTPException(status_code=404, detail="Block not found")

    try:
        await calendar_service.delete_calendar_block(
            current_user, db,
            calendar_id=block.calendar_id,
            account=block.account,  # type: ignore[arg-type]
            google_event_id=block.google_event_id,
        )
    except Exception:
        log.warning(
            "delete_task_block: failed to cancel GCal event %s for task %d block %d",
            block.google_event_id, task_id, block_id, exc_info=True,
        )
        # Soft-delete the DB row anyway so the chunk disappears from the UI.
        await calendar_block_repo.soft_delete(db, block_id)

    refreshed = await task_repo.get_by_id(db, task_id)
    return ok(await _task_read_with_next_start(db, refreshed))


@router.get("/archive", response_model=ApiResponse[list[TaskRead]], summary="List archived tasks")
async def list_archive(
    type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskRead]]:
    """Return done and delegated tasks, most recently completed first."""
    from app.models.task import TaskType as TT
    task_type = None
    if type is not None:
        try:
            task_type = TT(type)
        except ValueError:
            from fastapi import HTTPException as _HTTP
            raise _HTTP(status_code=400, detail="type must be 'work' or 'personal'")

    tasks = await task_repo.get_archive(db, current_user.id, task_type=task_type, limit=limit, offset=offset)
    reads = [TaskRead.model_validate(t) for t in tasks]
    return ok(reads, meta={"total": len(reads), "limit": limit, "offset": offset})
