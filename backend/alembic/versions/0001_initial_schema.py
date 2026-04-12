"""Initial schema: users, tasks, calendar_blocks, ai_estimation_log, scheduling_run_log

Revision ID: 0001
Revises:
Create Date: 2026-04-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    tasktype = postgresql.ENUM(
        "work", "personal", name="tasktype", create_type=False
    )
    taskstatus = postgresql.ENUM(
        "backlog",
        "scheduled",
        "tentatively_done",
        "done",
        "delegated",
        name="taskstatus",
        create_type=False,
    )
    scheduletrigger = postgresql.ENUM(
        "priority_change",
        "task_added",
        "task_deleted",
        "task_updated",
        "manual",
        "startup",
        name="scheduletrigger",
        create_type=False,
    )

    op.execute("CREATE TYPE tasktype AS ENUM ('work', 'personal')")
    op.execute(
        "CREATE TYPE taskstatus AS ENUM "
        "('backlog', 'scheduled', 'tentatively_done', 'done', 'delegated')"
    )
    op.execute(
        "CREATE TYPE scheduletrigger AS ENUM "
        "('priority_change', 'task_added', 'task_deleted', 'task_updated', 'manual', 'startup')"
    )

    # ── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Chicago"),
        # Work account OAuth tokens
        sa.Column("work_google_id", sa.String(255), nullable=True),
        sa.Column("work_access_token", sa.Text(), nullable=True),
        sa.Column("work_refresh_token", sa.Text(), nullable=True),
        sa.Column("work_token_expiry", sa.DateTime(timezone=True), nullable=True),
        # Personal account OAuth tokens
        sa.Column("personal_google_id", sa.String(255), nullable=True),
        sa.Column("personal_access_token", sa.Text(), nullable=True),
        sa.Column("personal_refresh_token", sa.Text(), nullable=True),
        sa.Column("personal_token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_work_google_id", "users", ["work_google_id"], unique=True)
    op.create_index(
        "ix_users_personal_google_id", "users", ["personal_google_id"], unique=True
    )

    # ── tasks ────────────────────────────────────────────────────────────────
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("type", tasktype, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", taskstatus, nullable=False, server_default="backlog"),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("optional_user_estimate", sa.String(255), nullable=True),
        sa.Column("actual_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("optional_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_off_hours_allowed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_workday_allowed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "part_of_task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "procrastination_flag", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_priority", "tasks", ["priority"])
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_status_priority", "tasks", ["status", "priority"])
    op.create_index("ix_tasks_created_at", "tasks", ["created_at"])
    op.create_index("ix_tasks_part_of_task_id", "tasks", ["part_of_task_id"])
    # Partial index: only rows where procrastination_flag is set (watchdog query)
    op.create_index(
        "ix_tasks_procrastination_flag",
        "tasks",
        ["procrastination_flag"],
        postgresql_where=sa.text("procrastination_flag = true"),
    )

    # ── calendar_blocks ───────────────────────────────────────────────────────
    op.create_table(
        "calendar_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("google_event_id", sa.String(255), nullable=False),
        sa.Column("calendar_id", sa.String(255), nullable=False),
        sa.Column("account", sa.String(16), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_calendar_blocks_task_id", "calendar_blocks", ["task_id"])
    op.create_index("ix_calendar_blocks_start_at", "calendar_blocks", ["start_at"])
    op.create_index("ix_calendar_blocks_is_deleted", "calendar_blocks", ["is_deleted"])
    op.create_index(
        "ix_calendar_blocks_google_event_id",
        "calendar_blocks",
        ["google_event_id"],
        unique=True,
    )
    # Partial index: active (non-deleted) blocks — the hot path for scheduler
    op.create_index(
        "ix_calendar_blocks_active_future",
        "calendar_blocks",
        ["is_deleted", "start_at"],
        postgresql_where=sa.text("is_deleted = false"),
    )

    # ── ai_estimation_log ─────────────────────────────────────────────────────
    op.create_table(
        "ai_estimation_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("task_type", sa.String(16), nullable=False),
        sa.Column("task_title_snapshot", sa.String(512), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("actual_minutes", sa.Integer(), nullable=True),
        sa.Column("error_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("ix_ai_estimation_log_task_id", "ai_estimation_log", ["task_id"])
    op.create_index("ix_ai_estimation_log_task_type", "ai_estimation_log", ["task_type"])
    op.create_index("ix_ai_estimation_log_created_at", "ai_estimation_log", ["created_at"])

    # ── scheduling_run_log ────────────────────────────────────────────────────
    op.create_table(
        "scheduling_run_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_reason", scheduletrigger, nullable=False),
        sa.Column(
            "triggered_by_task_id",
            sa.Integer(),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tasks_affected", sa.Integer(), nullable=True),
        sa.Column("blocks_deleted", sa.Integer(), nullable=True),
        sa.Column("blocks_created", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_scheduling_run_log_triggered_at", "scheduling_run_log", ["triggered_at"]
    )
    op.create_index(
        "ix_scheduling_run_log_triggered_by_task_id",
        "scheduling_run_log",
        ["triggered_by_task_id"],
    )


def downgrade() -> None:
    op.drop_table("scheduling_run_log")
    op.drop_table("ai_estimation_log")
    op.drop_table("calendar_blocks")
    op.drop_table("tasks")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS scheduletrigger")
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS tasktype")
