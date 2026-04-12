import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class TaskType(str, enum.Enum):
    work = "work"
    personal = "personal"


class TaskStatus(str, enum.Enum):
    backlog = "backlog"
    scheduled = "scheduled"
    tentatively_done = "tentatively_done"
    done = "done"
    delegated = "delegated"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # Fast backlog list view: ordered by priority, filtered by active statuses
        Index("ix_tasks_status_priority", "status", "priority"),
        # Watchdog query: tasks where procrastination_flag is set
        Index(
            "ix_tasks_procrastination_flag",
            "procrastination_flag",
            postgresql_where="procrastination_flag = true",
        ),
        # Watchdog candidate scan: incomplete tasks by created_at age
        Index("ix_tasks_created_at", "created_at"),
        # Split-task lookup: find continuations for a parent
        Index("ix_tasks_part_of_task_id", "part_of_task_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title = Column(String(512), nullable=False)
    type = Column(Enum(TaskType, name="tasktype"), nullable=False)
    # priority: 1 = highest. Sequential integers; full renumber on reorder.
    priority = Column(Integer, nullable=False, index=True)
    status = Column(
        Enum(TaskStatus, name="taskstatus"),
        nullable=False,
        default=TaskStatus.backlog,
        index=True,
    )

    # Duration fields
    estimated_duration_minutes = Column(Integer, nullable=True)  # AI-generated
    optional_user_estimate = Column(String(255), nullable=True)  # free-form AI input
    actual_duration_minutes = Column(Integer, nullable=True)     # filled on completion

    # Scheduling constraints
    optional_deadline = Column(DateTime(timezone=True), nullable=True)
    is_off_hours_allowed = Column(Boolean, nullable=False, default=False)
    is_workday_allowed = Column(Boolean, nullable=False, default=False)
    last_scheduled_at = Column(DateTime(timezone=True), nullable=True)

    # Part-of relationship (split tasks / Part 2 continuations)
    part_of_task_id = Column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )

    procrastination_flag = Column(Boolean, nullable=False, default=False, index=True)

    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="tasks", lazy="raise")
    calendar_blocks = relationship(
        "CalendarBlock",
        back_populates="task",
        lazy="raise",
        cascade="all, delete-orphan",
        order_by="CalendarBlock.start_at",
    )
    parent_task = relationship(
        "Task",
        remote_side="Task.id",
        foreign_keys="Task.part_of_task_id",
        lazy="raise",
    )
    continuation_tasks = relationship(
        "Task",
        foreign_keys="Task.part_of_task_id",
        lazy="raise",
        overlaps="parent_task",
    )
    ai_estimation_logs = relationship(
        "AIEstimationLog",
        back_populates="task",
        lazy="raise",
        cascade="all, delete-orphan",
    )
