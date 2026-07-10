from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CalendarBlock(Base):
    """
    Tracks every Google Calendar event FlowList has created.
    The app ONLY deletes/modifies events it owns — this table is the source of truth
    for which event IDs belong to FlowList.
    """

    __tablename__ = "calendar_blocks"
    __table_args__ = (
        # Primary access pattern: all active (non-deleted) future blocks
        Index(
            "ix_calendar_blocks_active_future",
            "is_deleted",
            "start_at",
            postgresql_where="is_deleted = false",
        ),
        # Lookup by Google event ID (e.g., when Google sends a webhook)
        Index("ix_calendar_blocks_google_event_id", "google_event_id", unique=True),
        # Lookup synthesis blocks by the meeting that spawned them
        Index("ix_calendar_blocks_source_event", "source_google_event_id"),
    )

    id = Column(Integer, primary_key=True)
    # Task that owns this block. NULL for synthesis blocks (they follow a
    # meeting, not a task).
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Direct owner. Always set on new blocks; lets us query a user's synthesis
    # blocks (which have no task) without a join.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # "task" (auto-scheduled backlog block) or "synthesis" (post-meeting buffer)
    block_type = Column(
        String(16), nullable=False, default="task", server_default="task"
    )
    # For synthesis blocks: the Google event ID of the meeting they follow.
    # Used to reconcile synthesis blocks idempotently across reschedule runs.
    source_google_event_id = Column(String(255), nullable=True)

    # Google Calendar identifiers
    google_event_id = Column(String(255), nullable=False)
    # The calendar the event was created on (work email or personal email)
    calendar_id = Column(String(255), nullable=False)
    # Which OAuth account was used to create it: "work" | "personal"
    account = Column(String(16), nullable=False)

    start_at = Column(DateTime(timezone=True), nullable=False, index=True)
    end_at = Column(DateTime(timezone=True), nullable=False)

    # Soft-delete: we mark blocks deleted here before/after removing from GCal.
    # Keeping the row preserves scheduling history.
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    task = relationship("Task", back_populates="calendar_blocks", lazy="raise")
