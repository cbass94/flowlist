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
    )

    id = Column(Integer, primary_key=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
