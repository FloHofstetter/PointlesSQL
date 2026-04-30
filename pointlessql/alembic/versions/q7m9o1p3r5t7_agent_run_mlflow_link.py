"""agent_run mlflow_run_id link (Phase 21.2)

Adds nullable ``mlflow_run_id`` columns to ``agent_runs`` and
``agent_run_operations`` so the cross-link layer in
:mod:`pointlessql.services.agent_runs.mlflow_detector` can correlate
PointlesSQL audit-trail entries with MLflow Tracking runs.

Existing rows stay ``NULL`` — there is no backfill because the
linkage is forward-looking. A future migration may decide to mine
``params_json`` for embedded MLflow run-ids and backfill, but the
cost outweighs the benefit (linkage on historical rows is rarely
queried).

Revision ID: q7m9o1p3r5t7
Revises: p6l8n0q3s5u7
Create Date: 2026-04-30 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q7m9o1p3r5t7"
down_revision: str | None = "p6l8n0q3s5u7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``mlflow_run_id`` columns + indexes to the two audit tables."""
    op.add_column(
        "agent_runs",
        sa.Column("mlflow_run_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_agent_runs_mlflow_run_id",
        "agent_runs",
        ["mlflow_run_id"],
    )
    op.add_column(
        "agent_run_operations",
        sa.Column("mlflow_run_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_agent_run_operations_mlflow_run_id",
        "agent_run_operations",
        ["mlflow_run_id"],
    )


def downgrade() -> None:
    """Drop the indexes + columns added in :func:`upgrade`."""
    op.drop_index("ix_agent_run_operations_mlflow_run_id", "agent_run_operations")
    op.drop_column("agent_run_operations", "mlflow_run_id")
    op.drop_index("ix_agent_runs_mlflow_run_id", "agent_runs")
    op.drop_column("agent_runs", "mlflow_run_id")
