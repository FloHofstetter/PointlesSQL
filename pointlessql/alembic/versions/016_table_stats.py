"""Sprint 56: table_stats for cached column profiling.

Revision ID: 016
Revises: 015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``table_stats`` cache table.

    Keyed by ``(full_name, delta_log_version, column_name)`` so that
    once a table has been profiled at a given Delta log version, the
    same version is served from the cache indefinitely — column
    statistics do not change unless the Delta table itself changes.
    ``stats_json`` stores the entire per-column dict verbatim to keep
    the schema flat.
    """
    op.create_table(
        "table_stats",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(length=500), nullable=False),
        sa.Column("delta_log_version", sa.BigInteger, nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("stats_json", sa.Text, nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.UniqueConstraint(
            "full_name", "delta_log_version", "column_name",
            name="uq_table_stats_col_version",
        ),
    )
    op.create_index(
        "ix_table_stats_lookup",
        "table_stats",
        ["full_name", "delta_log_version"],
    )


def downgrade() -> None:
    """Drop the ``table_stats`` cache table."""
    op.drop_index("ix_table_stats_lookup", table_name="table_stats")
    op.drop_table("table_stats")
