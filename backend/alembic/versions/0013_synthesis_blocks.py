"""Synthesis time blocks: extend calendar_blocks + user synthesis settings

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-09

Adds support for "Synthesis time" auto-blocks placed immediately after
multi-person meetings:
  - calendar_blocks gains block_type ('task' | 'synthesis'), a direct user_id
    (synthesis blocks have no task), and source_google_event_id (the meeting
    that spawned the block). task_id becomes nullable.
  - users gains synthesis_enabled, synthesis_duration_minutes, and
    synthesis_self_emails (comma-separated "these emails are me" list).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── calendar_blocks ──────────────────────────────────────────────────────
    op.add_column(
        "calendar_blocks",
        sa.Column(
            "block_type",
            sa.String(length=16),
            nullable=False,
            server_default="task",
        ),
    )
    op.add_column(
        "calendar_blocks",
        sa.Column("user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "calendar_blocks",
        sa.Column("source_google_event_id", sa.String(length=255), nullable=True),
    )
    op.create_foreign_key(
        "fk_calendar_blocks_user_id",
        "calendar_blocks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_calendar_blocks_user_id", "calendar_blocks", ["user_id"])
    op.create_index(
        "ix_calendar_blocks_source_event",
        "calendar_blocks",
        ["source_google_event_id"],
    )

    # Backfill user_id on existing (task) blocks from their task's owner
    op.execute(
        """
        UPDATE calendar_blocks AS cb
        SET user_id = t.user_id
        FROM tasks AS t
        WHERE cb.task_id = t.id AND cb.user_id IS NULL
        """
    )

    # task_id becomes nullable (synthesis blocks have no task)
    op.alter_column("calendar_blocks", "task_id", existing_type=sa.Integer(), nullable=True)

    # ── users: synthesis settings ────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "synthesis_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "synthesis_duration_minutes",
            sa.Integer(),
            nullable=False,
            server_default="15",
        ),
    )
    op.add_column(
        "users",
        sa.Column("synthesis_self_emails", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "synthesis_self_emails")
    op.drop_column("users", "synthesis_duration_minutes")
    op.drop_column("users", "synthesis_enabled")

    op.alter_column("calendar_blocks", "task_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_calendar_blocks_source_event", table_name="calendar_blocks")
    op.drop_index("ix_calendar_blocks_user_id", table_name="calendar_blocks")
    op.drop_constraint("fk_calendar_blocks_user_id", "calendar_blocks", type_="foreignkey")
    op.drop_column("calendar_blocks", "source_google_event_id")
    op.drop_column("calendar_blocks", "user_id")
    op.drop_column("calendar_blocks", "block_type")
