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
    CompleteRequest,
    ReorderRequest,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)
from app.services import ai_service, calendar_service
from app.services.auth_service import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_DEBOUNCE_KEY = "reschedule:token:{user_id}"
_TERMINAL_STATUSES = [TaskStatus.done, TaskStatus.delegated]
_RESCHEDULE_FIELDS = {"estimated_duration_minutes", "type", "is_off_hours_allowed", "is_workday_allowed"}


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
    reads = [
        TaskRead.model_validate(t).model_copy(update={"next_scheduled_start": next_starts.get(t.id)})
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
        part_of_task_id=body.part_of_task_id,
        notes=body.notes,
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
    return ok(TaskRead.model_validate(task))


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

    changed_fields = set(body.model_dump(exclude_unset=True).keys())
    if changed_fields & _RESCHEDULE_FIELDS:
        await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_updated)

    return ok(TaskRead.model_validate(task))


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
    task = await task_repo.get_by_id(db, task_id)
    if task is None or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    task = await task_repo.mark_complete(
        db, task_id, actual_duration_minutes=body.actual_duration_minutes
    )
    if body.actual_duration_minutes:
        await ai_service.record_task_completion(
            db, task_id, body.actual_duration_minutes
        )

    return ok(TaskRead.model_validate(task))


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
    return ok(TaskRead.model_validate(task))


@router.post("/{task_id}/create-part2", response_model=ApiResponse[TaskRead], summary="Create Part 2 continuation")
async def create_part2(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskRead]:
    original = await task_repo.get_by_id(db, task_id)
    if original is None or original.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    continuation = await task_repo.create(
        db,
        user_id=current_user.id,
        title=f"{original.title} — Part 2",
        task_type=original.type,
        priority=original.priority,
        estimated_duration_minutes=original.estimated_duration_minutes,
        part_of_task_id=original.id,
    )
    await task_repo.update_fields(db, task_id, priority=original.priority + 1)
    await _enqueue_reschedule(current_user.id, ScheduleTrigger.task_added)
    return ok(TaskRead.model_validate(continuation))


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
