"""AI calendar color-coding: event_colors table + user colorize settings

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-10

Adds support for classifying calendar events into four productivity buckets and
setting the Google Calendar event color:
  - event_colors: caches each event's classification (so we don't re-call Claude
    for unchanged events) and records which events FlowList colored (so manual
    color edits are respected).
  - users: colorize_enabled (opt-in, default off) + a configurable colorId per
    bucket.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_colors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("calendar_id", sa.String(length=255), nullable=False),
        sa.Column("google_event_id", sa.String(length=255), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("applied_color_id", sa.String(length=2), nullable=False),
        sa.Column("content_signature", sa.String(length=64), nullable=False),
        sa.Column(
            "is_user_overridden",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "google_event_id", name="uq_event_colors_user_event"
        ),
    )
    op.create_index("ix_event_colors_user_id", "event_colors", ["user_id"])

    op.add_column(
        "users",
        sa.Column(
            "colorize_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "users",
        sa.Column("color_purposeful", sa.String(length=2), nullable=False, server_default="10"),
    )
    op.add_column(
        "users",
        sa.Column("color_necessary", sa.String(length=2), nullable=False, server_default="7"),
    )
    op.add_column(
        "users",
        sa.Column("color_distracting", sa.String(length=2), nullable=False, server_default="11"),
    )
    op.add_column(
        "users",
        sa.Column("color_unnecessary", sa.String(length=2), nullable=False, server_default="8"),
    )


def downgrade() -> None:
    op.drop_column("users", "color_unnecessary")
    op.drop_column("users", "color_distracting")
    op.drop_column("users", "color_necessary")
    op.drop_column("users", "color_purposeful")
    op.drop_column("users", "colorize_enabled")
    op.drop_index("ix_event_colors_user_id", table_name="event_colors")
    op.drop_table("event_colors")
