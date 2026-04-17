"""Create jobs, job_runs, job_tasks, job_logs tables.

Revision ID: 005
Revises: 004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Sprint 19 job scheduler tables.

    ``job_tasks`` and ``job_logs`` are created empty; Sprint 20 adds
    ``depends_on`` / ``retries`` columns and populates ``job_logs`` per
    task. Pre-creating them now keeps that sprint's migration additive.
    """
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("cron_expr", sa.String(120), nullable=False),
        sa.Column(
            "run_as_user_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("config", sa.Text, nullable=False, server_default="{}"),
        sa.Column("is_paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
    )
    # Supports the "most recent N runs for job X" query that powers the
    # detail-page run-history card. Postgres honours the DESC direction,
    # SQLite treats it as a hint but still uses the index for lookups.
    op.create_index(
        "ix_job_runs_job_started",
        "job_runs",
        ["job_id", sa.text("started_at DESC")],
    )

    op.create_table(
        "job_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("config", sa.Text, nullable=False, server_default="{}"),
    )

    op.create_table(
        "job_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "job_run_id",
            sa.Integer,
            sa.ForeignKey("job_runs.id"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
    )


def downgrade() -> None:
    """Drop all Sprint 19 scheduler tables."""
    op.drop_table("job_logs")
    op.drop_table("job_tasks")
    op.drop_index("ix_job_runs_job_started", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_table("jobs")
