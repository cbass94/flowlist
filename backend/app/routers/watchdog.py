"""
Watchdog router — exposes the procrastination-flagged task list.

GET /api/watchdog
    Returns all tasks where procrastination_flag is True for the current user.
    The flag is set by the nightly ARQ cron job when a task has been in the
    backlog for more than WATCHDOG_THRESHOLD_DAYS without being completed.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.repositories import calendar_block_repo, task_repo
from app.schemas.envelope import ApiResponse, ok
from app.schemas.task import TaskBlockInfo, TaskRead
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/watchdog", tags=["watchdog"])


@router.get("/", response_model=ApiResponse[list[TaskRead]], summary="List procrastinating tasks")
async def get_watchdog_tasks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TaskRead]]:
    """Return all tasks currently flagged as procrastinated."""
    tasks = await task_repo.get_procrastination_flagged(db, current_user.id)
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
