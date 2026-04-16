"""Extend job_tasks with DAG + retry columns, add task_runs, expand jobs.

Revision ID: 006
Revises: 005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Grow Sprint 19's placeholder schema into a full DAG engine.

    Three changes, each idempotent against the Sprint 19 baseline:

    * ``jobs.max_parallel_runs`` — per-job concurrency ceiling; default
      1 preserves Sprint 19's "one at a time" behavior.
    * ``job_tasks`` gains ``depends_on`` (JSON-as-text list of task
      ids), ``max_retries`` and ``retry_backoff_seconds``. The Sprint 19
      ``order`` column stays — it is unused by the DAG walker but
      keeping it avoids a destructive drop-and-recreate.
    * ``task_runs`` — new table holding per-task state (``pending`` |
      ``running`` | ``succeeded`` | ``failed`` | ``skipped``) plus
      retry counter and last-error snapshot. ``job_logs`` keeps its
      Sprint 19 shape, just gains a ``task_id`` FK so the log viewer
      can filter per task.
    """
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(
            sa.Column(
                "max_parallel_runs",
                sa.Integer,
                nullable=False,
                server_default="1",
            )
        )

    with op.batch_alter_table("job_tasks") as batch:
        batch.add_column(
            sa.Column(
                "depends_on",
                sa.Text,
                nullable=False,
                server_default="[]",
            )
        )
        batch.add_column(
            sa.Column(
                "max_retries",
                sa.Integer,
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "retry_backoff_seconds",
                sa.Integer,
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "kind",
                sa.String(50),
                nullable=False,
                server_default="python",
            )
        )

    op.create_table(
        "task_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "job_run_id",
            sa.Integer,
            sa.ForeignKey("job_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey("job_tasks.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempts", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_task_runs_job_run",
        "task_runs",
        ["job_run_id"],
    )

    with op.batch_alter_table("job_logs") as batch:
        batch.add_column(
            sa.Column(
                "task_id",
                sa.Integer,
                sa.ForeignKey(
                    "job_tasks.id", name="fk_job_logs_task_id"
                ),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Revert to the Sprint 19 schema."""
    with op.batch_alter_table("job_logs") as batch:
        batch.drop_column("task_id")

    op.drop_index("ix_task_runs_job_run", table_name="task_runs")
    op.drop_table("task_runs")

    with op.batch_alter_table("job_tasks") as batch:
        batch.drop_column("kind")
        batch.drop_column("retry_backoff_seconds")
        batch.drop_column("max_retries")
        batch.drop_column("depends_on")

    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("max_parallel_runs")
