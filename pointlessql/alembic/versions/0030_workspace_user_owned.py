"""workspace_id on user-owned + scheduler tables

Sprint 28.2 — extends workspace_id to every user-owned and
scheduler-side table.  After this migration a workspace-A user
sees only workspace-A's jobs / dashboards / saved queries / saved
audit queries / recent tables / alerts / notebook outputs.

Tables touched (13):

* ``jobs``, ``job_runs``, ``job_tasks``, ``task_runs``, ``job_logs``
* ``dashboards``, ``saved_queries``, ``saved_audit_queries``
* ``recent_tables`` (UNIQUE constraint widened from
  ``(user_id, table_full_name)`` to
  ``(workspace_id, user_id, table_full_name)``)
* ``alerts``, ``alert_events``
* ``notebook_outputs``, ``notebook_cell_runs``

Every column adds with ``server_default='1'`` so existing rows
backfill to the seeded default workspace.

Backfill order: jobs.workspace_id := users[run_as_user_id].
default_workspace_id (or 1).  Child tables (job_runs / task_runs /
job_logs) cascade from parent jobs.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-05 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table_name, index_name, [index_cols]).
_TABLES_AND_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("jobs", "ix_jobs_workspace_user", ["workspace_id", "run_as_user_id"]),
    ("job_runs", "ix_job_runs_workspace_started", ["workspace_id", "started_at"]),
    ("job_tasks", "ix_job_tasks_workspace_job", ["workspace_id", "job_id"]),
    ("task_runs", "ix_task_runs_workspace_job_run", ["workspace_id", "job_run_id"]),
    ("job_logs", "ix_job_logs_workspace_ts", ["workspace_id", "ts"]),
    ("dashboards", "ix_dashboards_workspace_owner", ["workspace_id", "owner_id"]),
    ("saved_queries", "ix_saved_queries_workspace_owner", ["workspace_id", "owner_id"]),
    (
        "saved_audit_queries",
        "ix_saved_audit_queries_workspace",
        ["workspace_id"],
    ),
    ("alerts", "ix_alerts_workspace_owner", ["workspace_id", "owner_id"]),
    ("alert_events", "ix_alert_events_workspace_alert", ["workspace_id", "alert_id"]),
    (
        "notebook_outputs",
        "ix_notebook_outputs_workspace_path",
        ["workspace_id", "file_path"],
    ),
    (
        "notebook_cell_runs",
        "ix_notebook_cell_runs_workspace_session",
        ["workspace_id", "kernel_session_id"],
    ),
)


def upgrade() -> None:
    """Add workspace_id columns + indexes; widen recent_tables UNIQUE."""
    bind = op.get_bind()

    # 1. Plain workspace_id additions ---------------------------------------
    for table_name, _index_name, _index_cols in _TABLES_AND_INDEXES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "workspace_id",
                    sa.Integer(),
                    sa.ForeignKey("workspaces.id", name=f"fk_{table_name}_workspace_id"),
                    nullable=False,
                    server_default="1",
                )
            )

    # 2. recent_tables: workspace_id + UNIQUE constraint widening -----------
    with op.batch_alter_table("recent_tables") as batch_op:
        batch_op.add_column(
            sa.Column(
                "workspace_id",
                sa.Integer(),
                sa.ForeignKey("workspaces.id", name="fk_recent_tables_workspace_id"),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.drop_constraint("uq_recent_tables_user_table", type_="unique")
        batch_op.create_unique_constraint(
            "uq_recent_tables_user_table",
            ["workspace_id", "user_id", "table_full_name"],
        )

    # 3. Backfill jobs.workspace_id from owning user's default workspace ----
    bind.execute(
        sa.text(
            "UPDATE jobs SET workspace_id = COALESCE("
            "(SELECT default_workspace_id FROM users WHERE users.id = jobs.run_as_user_id), 1)"
        )
    )
    # Cascade child tables from the parent job.  SQLite UPDATE...FROM is
    # supported since 3.33 (we run SQLite 3.46+); Postgres has it too.
    bind.execute(
        sa.text(
            "UPDATE job_runs SET workspace_id = COALESCE("
            "(SELECT workspace_id FROM jobs WHERE jobs.id = job_runs.job_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE job_tasks SET workspace_id = COALESCE("
            "(SELECT workspace_id FROM jobs WHERE jobs.id = job_tasks.job_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE task_runs SET workspace_id = COALESCE("
            "(SELECT workspace_id FROM job_runs WHERE job_runs.id = task_runs.job_run_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE job_logs SET workspace_id = COALESCE("
            "(SELECT workspace_id FROM job_runs WHERE job_runs.id = job_logs.job_run_id), 1)"
        )
    )

    # User-owned tables backfill from owner_id → user.default.
    bind.execute(
        sa.text(
            "UPDATE dashboards SET workspace_id = COALESCE("
            "(SELECT default_workspace_id FROM users WHERE users.id = dashboards.owner_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE saved_queries SET workspace_id = COALESCE("
            "(SELECT default_workspace_id FROM users WHERE users.id = saved_queries.owner_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE alerts SET workspace_id = COALESCE("
            "(SELECT default_workspace_id FROM users WHERE users.id = alerts.owner_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE alert_events SET workspace_id = COALESCE("
            "(SELECT workspace_id FROM alerts WHERE alerts.id = alert_events.alert_id), 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE recent_tables SET workspace_id = COALESCE("
            "(SELECT default_workspace_id FROM users WHERE users.id = recent_tables.user_id), 1)"
        )
    )
    # Belt-and-braces NULL sweep for everything else (server_default did
    # the bulk; this catches manual-DB edge cases).
    for tname, _, _ in _TABLES_AND_INDEXES:
        bind.execute(sa.text(f"UPDATE {tname} SET workspace_id = 1 WHERE workspace_id IS NULL"))
    bind.execute(sa.text("UPDATE recent_tables SET workspace_id = 1 WHERE workspace_id IS NULL"))

    # 4. Compound indexes ---------------------------------------------------
    for table_name, index_name, index_cols in _TABLES_AND_INDEXES:
        op.create_index(index_name, table_name, index_cols)
    op.create_index(
        "ix_recent_tables_workspace_user",
        "recent_tables",
        ["workspace_id", "user_id"],
    )


def downgrade() -> None:
    """Drop indexes + workspace_id columns; restore recent_tables UNIQUE."""
    for table_name, index_name, _ in _TABLES_AND_INDEXES:
        op.drop_index(index_name, table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("workspace_id")

    op.drop_index("ix_recent_tables_workspace_user", table_name="recent_tables")
    with op.batch_alter_table("recent_tables") as batch_op:
        batch_op.drop_constraint("uq_recent_tables_user_table", type_="unique")
        batch_op.create_unique_constraint(
            "uq_recent_tables_user_table",
            ["user_id", "table_full_name"],
        )
        batch_op.drop_column("workspace_id")
