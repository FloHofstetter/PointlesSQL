"""Sprint 13.2: agent_runs table + FK columns on notebook tables.

Revision ID: 020
Revises: 019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``agent_runs`` and link the notebook persistence tables to it.

    Phase 13 treats PointlesSQL as a registry + store for agent runs
    (Hermes or another runtime owns execution).  The table captures
    one row per run that an external runtime POSTs in: who (principal
    + agent_id), what (notebook_path + content snapshot), how far
    (status, cost_est, tables_touched), and the approval state for
    the Sprint-13.4 control-room.  The two FK columns on
    ``notebook_outputs`` / ``notebook_cell_runs`` let the run-detail
    view join outputs + cell lifecycle back to their owning run
    without guessing via ``kernel_session_id`` heuristics.  Both FKs
    are nullable — legacy rows from the deleted browser editor
    stay reachable, and a run can be created before the runtime has
    emitted any per-cell data.
    """
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("principal", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("notebook_path", sa.String(length=1024), nullable=False),
        sa.Column("source_snapshot_sha", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("cost_est", sa.Numeric(18, 4), nullable=True),
        sa.Column("tables_touched", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("denied_reason", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_agent_runs_started_at",
        "agent_runs",
        ["started_at"],
    )
    op.create_index(
        "ix_agent_runs_principal",
        "agent_runs",
        ["principal"],
    )
    op.create_index(
        "ix_agent_runs_status",
        "agent_runs",
        ["status"],
    )

    with op.batch_alter_table("notebook_outputs") as batch:
        batch.add_column(sa.Column("agent_run_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_notebook_outputs_agent_run",
        "notebook_outputs",
        ["agent_run_id"],
    )

    with op.batch_alter_table("notebook_cell_runs") as batch:
        batch.add_column(sa.Column("agent_run_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_notebook_cell_runs_agent_run",
        "notebook_cell_runs",
        ["agent_run_id"],
    )


def downgrade() -> None:
    """Drop the Sprint 13.2 agent-runs surface."""
    op.drop_index("ix_notebook_cell_runs_agent_run", table_name="notebook_cell_runs")
    with op.batch_alter_table("notebook_cell_runs") as batch:
        batch.drop_column("agent_run_id")

    op.drop_index("ix_notebook_outputs_agent_run", table_name="notebook_outputs")
    with op.batch_alter_table("notebook_outputs") as batch:
        batch.drop_column("agent_run_id")

    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_principal", table_name="agent_runs")
    op.drop_index("ix_agent_runs_started_at", table_name="agent_runs")
    op.drop_table("agent_runs")
