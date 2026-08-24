from sqlalchemy import (
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


class BucketOverride(Base):
    """
    A durable correction to FlowList's productivity-bucket classification.

    Where event_colors records what FlowList *did* to one specific calendar
    event, a bucket override records what the user *wants* for a whole class of
    events — and outlives any individual event ID.

    Two jobs:
      1. Deterministic pre-empt. colorize_user resolves overrides before calling
         Claude, so a corrected event is never re-classified (and never drifts
         back to the bucket the user rejected).
      2. Teaching. Recent overrides are fed into the classify prompt as
         corrections, so genuinely new but similar events land in the right
         bucket the first time.

    Scope determines what match_key holds, and the three are tried in this order
    (see colorize.override_key_candidates):

      task    task ID, as a string. Task blocks are soft-deleted and recreated
              with fresh google_event_ids on every reschedule, so the task is
              the only identity that survives.
      series  the Google recurringEventId. Covers every instance of a recurring
              meeting, including ones not yet in the lookahead window.
      title   the normalized event summary. Catches one-off events and anything
              similar the user hasn't seen yet.
    """

    __tablename__ = "bucket_overrides"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "match_key", name="uq_bucket_overrides_key"),
        Index("ix_bucket_overrides_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # One of: task | series | title
    scope = Column(String(8), nullable=False)
    # Task ID / recurringEventId / normalized title, per scope
    match_key = Column(String(255), nullable=False)

    # The bucket the user wants. One of colorize.BUCKETS.
    bucket = Column(String(16), nullable=False)
    # What the AI had said, when we know it. Turns the prompt hint into a real
    # correction ("not X, actually Y") rather than a bare label. Nullable —
    # overrides set before any classification have nothing to correct.
    was_bucket = Column(String(16), nullable=True)
    # A human-readable event/task title, for the corrections block in the prompt.
    example_summary = Column(String(512), nullable=True)
    # Where the correction came from: app | gcal
    source = Column(String(8), nullable=False, default="app")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
