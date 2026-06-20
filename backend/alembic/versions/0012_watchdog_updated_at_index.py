"""Replace ix_tasks_created_at with ix_tasks_updated_at for watchdog query

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_tasks_created_at", table_name="tasks")
    op.create_index("ix_tasks_updated_at", "tasks", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_tasks_updated_at", table_name="tasks")
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
