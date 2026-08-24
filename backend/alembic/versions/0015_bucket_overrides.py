"""Bucket overrides: durable user corrections to calendar color classification

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-23

Adds bucket_overrides, which records what bucket the user wants for a class of
events (a task, a recurring series, or a normalized title) rather than for one
event ID. colorize_user consults these before calling Claude, and feeds the
recent ones back into the classify prompt as corrections.

No SQL backfill. Existing event_colors rows flagged is_user_overridden are past
corrections whose meaning was discarded, and they are worth recovering — but
event_colors stores no event title and no series ID, so there is nothing here to
build a match_key from. That recovery happens at runtime instead: the first
colorize run after this migration reconsiders each ceded event once, and the
adopt path in colorize_service records a real override using the live event's
title and recurringEventId.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bucket_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(length=8), nullable=False),
        sa.Column("match_key", sa.String(length=255), nullable=False),
        sa.Column("bucket", sa.String(length=16), nullable=False),
        sa.Column("was_bucket", sa.String(length=16), nullable=True),
        sa.Column("example_summary", sa.String(length=512), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False, server_default="app"),
        sa.Column(
            "created_at",
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
            "user_id", "scope", "match_key", name="uq_bucket_overrides_key"
        ),
    )
    op.create_index("ix_bucket_overrides_user_id", "bucket_overrides", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bucket_overrides_user_id", table_name="bucket_overrides")
    op.drop_table("bucket_overrides")
