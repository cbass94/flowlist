"""
Repository layer — typed async functions for all database operations.

Usage pattern (in a route or service):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            task = await task_repo.create(session, user_id=1, title="...", ...)
            await ai_log_repo.log_estimation(session, task_id=task.id, ...)
            # session.begin() commits on exit, rolls back on exception
"""

from app.repositories import (
    ai_log_repo,
    calendar_block_repo,
    scheduling_log_repo,
    task_repo,
    user_repo,
)

__all__ = [
    "user_repo",
    "task_repo",
    "calendar_block_repo",
    "ai_log_repo",
    "scheduling_log_repo",
]
