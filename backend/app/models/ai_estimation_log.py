from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AIEstimationLog(Base):
    """
    Records every AI duration estimate alongside the eventual actual duration.
    Used to provide historical context back to the AI so it improves over time.
    One row per task (created when AI estimates; actual_minutes filled on completion).
    """

    __tablename__ = "ai_estimation_log"

    id = Column(Integer, primary_key=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,   # kept after task deletion for training history
        index=True,
    )

    # Snapshot of task data at estimation time (task may be edited or deleted later)
    task_type = Column(String(16), nullable=False, index=True)  # "work" | "personal"
    task_title_snapshot = Column(String(512), nullable=False)

    # Keywords extracted by AI for pattern-matching across similar tasks
    keywords = Column(ARRAY(Text), nullable=True)

    # The actual estimate and model used
    estimated_minutes = Column(Integer, nullable=False)
    model_used = Column(String(64), nullable=False)

    # Filled in when task is marked complete (via Task.actual_duration_minutes)
    actual_minutes = Column(Integer, nullable=True)

    # Derived: how far off was the estimate? (actual - estimated); app-computed on update.
    error_minutes = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    task = relationship("Task", back_populates="ai_estimation_logs", lazy="raise")
