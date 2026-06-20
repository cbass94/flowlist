"""Add per-day weekend hour ranges to users

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    "work_saturday_start_time",
    "work_saturday_end_time",
    "work_sunday_start_time",
    "work_sunday_end_time",
    "personal_saturday_start_time",
    "personal_saturday_end_time",
    "personal_sunday_start_time",
    "personal_sunday_end_time",
]


def upgrade() -> None:
    for col in _COLUMNS:
        op.add_column("users", sa.Column(col, sa.Time(), nullable=True))


def downgrade() -> None:
    for col in reversed(_COLUMNS):
        op.drop_column("users", col)
