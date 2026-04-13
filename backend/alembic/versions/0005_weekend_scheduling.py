"""Add weekend scheduling preferences to users

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("allow_work_on_weekends", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("allow_personal_on_weekends", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("users", "allow_personal_on_weekends")
    op.drop_column("users", "allow_work_on_weekends")
