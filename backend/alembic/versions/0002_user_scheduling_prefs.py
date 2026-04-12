"""Add scheduling preference columns to users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("work_start_hour", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("users", sa.Column("work_end_hour", sa.Integer(), nullable=False, server_default="17"))
    op.add_column("users", sa.Column("hard_start_hour", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("users", sa.Column("hard_end_hour", sa.Integer(), nullable=False, server_default="22"))
    op.add_column("users", sa.Column("buffer_minutes", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("users", sa.Column("work_calendar_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("personal_calendar_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "personal_calendar_id")
    op.drop_column("users", "work_calendar_id")
    op.drop_column("users", "buffer_minutes")
    op.drop_column("users", "hard_end_hour")
    op.drop_column("users", "hard_start_hour")
    op.drop_column("users", "work_end_hour")
    op.drop_column("users", "work_start_hour")
