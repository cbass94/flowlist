from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AIAssistantFeedback(Base):
    """
    Records user feedback on AI Assistant suggestions.
    Fed back into future AI Assistant prompts so the model learns
    what kinds of suggestions the user finds helpful or unhelpful.
    """

    __tablename__ = "ai_assistant_feedback"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    task_title_snapshot = Column(String(512), nullable=False)
    task_type = Column(String(16), nullable=False)

    is_positive = Column(Boolean, nullable=False)
    comment = Column(Text, nullable=True)

    ai_summary_snapshot = Column(Text, nullable=False)
    ai_suggestions_snapshot = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user = relationship("User", lazy="raise")
    task = relationship("Task", lazy="raise")
