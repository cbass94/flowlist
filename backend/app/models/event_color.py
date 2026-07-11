from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


class EventColor(Base):
    """
    Records FlowList's color-coding of a Google Calendar event.

    Two jobs:
      1. Cache the AI classification (via content_signature) so unchanged events
         are never re-sent to Claude.
      2. Track which events FlowList colored so manual color edits by the user
         are respected — if the event's current color no longer matches
         applied_color_id, the user changed it and we stop managing it
         (is_user_overridden = True).

    Unlike calendar_blocks (events FlowList *created*), these rows point at
    events FlowList only *recolors* — including received invites it does not own.
    """

    __tablename__ = "event_colors"
    __table_args__ = (
        UniqueConstraint("user_id", "google_event_id", name="uq_event_colors_user_event"),
        Index("ix_event_colors_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    calendar_id = Column(String(255), nullable=False)
    google_event_id = Column(String(255), nullable=False)

    # One of: purposeful | necessary | distracting | unnecessary
    bucket = Column(String(16), nullable=False)
    # The Google colorId FlowList last wrote for this event
    applied_color_id = Column(String(2), nullable=False)
    # Hash of the classification-relevant fields; changes ⇒ re-classify
    content_signature = Column(String(64), nullable=False)
    # Set once the user changes the color themselves — we then leave it alone
    is_user_overridden = Column(Boolean, nullable=False, default=False)

    classified_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
