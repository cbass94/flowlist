"""
AI Assistant feedback repository.

Stores and retrieves user feedback on AI Assistant suggestions.
Recent feedback is injected into future AI Assistant prompts so the
model can learn the user's preferences over time.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_assistant_feedback import AIAssistantFeedback


async def create(
    session: AsyncSession,
    user_id: int,
    task_id: int | None,
    task_title_snapshot: str,
    task_type: str,
    is_positive: bool,
    comment: str | None,
    ai_summary_snapshot: str,
    ai_suggestions_snapshot: str,
) -> AIAssistantFeedback:
    entry = AIAssistantFeedback(
        user_id=user_id,
        task_id=task_id,
        task_title_snapshot=task_title_snapshot,
        task_type=task_type,
        is_positive=is_positive,
        comment=comment,
        ai_summary_snapshot=ai_summary_snapshot,
        ai_suggestions_snapshot=ai_suggestions_snapshot,
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_recent(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[AIAssistantFeedback]:
    """Fetch recent feedback entries for prompt context injection."""
    result = await session.execute(
        select(AIAssistantFeedback)
        .where(AIAssistantFeedback.user_id == user_id)
        .order_by(AIAssistantFeedback.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
