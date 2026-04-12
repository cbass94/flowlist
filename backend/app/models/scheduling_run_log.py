import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.sql import func

from app.database import Base


class ScheduleTrigger(str, enum.Enum):
    priority_change = "priority_change"  # user reordered backlog
    task_added = "task_added"            # new task created
    task_deleted = "task_deleted"        # task removed
    task_updated = "task_updated"        # type/duration/constraints changed
    manual = "manual"                    # user pressed "Reschedule All"
    startup = "startup"                  # app startup sync


class SchedulingRunLog(Base):
    """
    Audit log for every full reschedule run.
    Useful for debugging scheduling issues and understanding how often reshuffles happen.
    """

    __tablename__ = "scheduling_run_log"

    id = Column(Integer, primary_key=True)

    triggered_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    trigger_reason = Column(
        Enum(ScheduleTrigger, name="scheduletrigger"), nullable=False
    )
    # Which task caused the trigger (null for manual/startup)
    triggered_by_task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Counters — filled in on completion
    tasks_affected = Column(Integer, nullable=True)
    blocks_deleted = Column(Integer, nullable=True)
    blocks_created = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Null on success; error message/traceback on failure
    error = Column(Text, nullable=True)
