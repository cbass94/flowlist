"""
Review prompts router — tasks awaiting the "done or need more time?" decision.

GET  /api/review-prompts/                  → list all tentatively_done tasks
POST /api/review-prompts/{id}/confirm      → mark task done
POST /api/review-prompts/{id}/reschedule   → create Part 2 continuation
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.scheduling_run_log import ScheduleTrigger
from app.models.user import User
from app.repositories import calendar_block_repo, task_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.task import CompleteRequest, TaskRead
from app.services import ai_service
from app.services.auth_service import get_current_user
from app.routers.tasks import _enqueue_reschedule

router = APIRouter(prefix="/api/review-prompts", tags=["review-prompts"])


@router.get("/", response_model=ApiResponse[list[TaskRead]], summary="List review prompts")
async def list_review_prompts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskRead]]:
    tasks = await task_repo.get_tentatively_done(db, current_user.id)
    task_ids = [t.id for t in tasks]
    next_starts = await calendar_block_repo.get_earliest_start_by_task_ids(db, task_ids)
    reads = [
        TaskRead.model_validate(t).model_copy(update={"next_scheduled_start": next_starts.get(t.id)})
        for t in tasks
    ]
    return ok(reads, meta={"total": len(reads)})


@router.post(
    "/{task_id}/confirm",
    response_model=ApiResponse[TaskRead],
    summary="Confirm task complete",
)
async def confirm_task(
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


@router.post(
    "/{task_id}/reschedule",
    response_model=ApiResponse[TaskRead],
    summary="Reschedule task (create Part 2)",
)
async def reschedule_task(
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
