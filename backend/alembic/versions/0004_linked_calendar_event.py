"""Add linked calendar event fields to tasks

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("linked_calendar_event_id", sa.String(255), nullable=True))
    op.add_column("tasks", sa.Column("linked_calendar_event_title", sa.String(512), nullable=True))
    op.add_column("tasks", sa.Column("linked_calendar_event_start", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "linked_calendar_event_start")
    op.drop_column("tasks", "linked_calendar_event_title")
    op.drop_column("tasks", "linked_calendar_event_id")
