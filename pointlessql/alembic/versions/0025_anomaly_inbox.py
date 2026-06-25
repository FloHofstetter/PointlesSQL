"""anomaly inbox + per-run severity cache

Adds two thin columns to ``agent_runs`` (``anomaly_severity`` +
``anomaly_metric``) so the runs-list page can paint a badge without
re-running the aggregator at every render, and a new
``anomaly_acks`` table that holds the cross-run inbox's
acknowledgement / snooze state.

The columns are *NOT* live-computed in the migration via the audit
aggregator — that would couple the migration to the runtime
service layer.  Instead we bulk-set ``anomaly_severity`` to a
deterministic per-row sentinel (``NULL``) and let the run-finish
hook plus a one-shot CLI command repopulate them.  Production
deployments can run the CLI with
``pointlessql audit recompute-run-anomalies`` after upgrade if they
want the badge populated for historical runs immediately; otherwise
the badge appears organically as new runs finish.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two columns + ``anomaly_acks`` table."""
    op.add_column(
        "agent_runs",
        sa.Column("anomaly_severity", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("anomaly_metric", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "anomaly_acks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("bin_iso", sa.String(length=32), nullable=False),
        sa.Column("bin_kind", sa.String(length=8), nullable=False),
        sa.Column("group_value", sa.String(length=512), nullable=True),
        sa.Column("group_kind", sa.String(length=16), nullable=True),
        sa.Column("acked_by", sa.String(length=255), nullable=False),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "metric",
            "bin_iso",
            "bin_kind",
            "group_value",
            "group_kind",
            name="uq_anomaly_acks_identity",
        ),
    )
    op.create_index(
        "ix_anomaly_acks_acked_at",
        "anomaly_acks",
        ["acked_at"],
    )


def downgrade() -> None:
    """Drop the table + the two columns."""
    op.drop_index("ix_anomaly_acks_acked_at", table_name="anomaly_acks")
    op.drop_table("anomaly_acks")
    op.drop_column("agent_runs", "anomaly_metric")
    op.drop_column("agent_runs", "anomaly_severity")
