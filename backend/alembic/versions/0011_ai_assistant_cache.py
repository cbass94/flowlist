"""Add AI Assistant response cache columns to tasks

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("ai_assistant_cache", JSONB, nullable=True))
    op.add_column(
        "tasks",
        sa.Column("ai_assistant_cached_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "ai_assistant_cached_at")
    op.drop_column("tasks", "ai_assistant_cache")
