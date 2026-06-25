"""runtime-measured SLOs for the 4 decl-only kinds

Adds the persistence the runtime-SLO surface needs:

* ``data_product_slos.last_measured_at`` — wall-clock of the latest
  measurement, displayed in the SLO tab.
* ``data_product_slo_evaluations.measurement_detail_json`` — per-eval
  payload for drill-down (p95, sample size, etc.).
* ``data_product_availability_probes`` — probe-based availability
  measurement (1 row per scheduled probe).
* ``data_product_query_perf_samples`` — per-SELECT performance
  samples; phase 146 will extend this table with cost columns.

Revision ID: 0130
Revises: 0129
Create Date: 2026-05-30 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0130"
down_revision: str | None = "0129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add columns + create the probe + perf-sample tables."""
    op.add_column(
        "data_product_slos",
        sa.Column("last_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_product_slos",
        sa.Column("last_measurement_detail_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "data_product_availability_probes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("output_port_id", sa.Integer(), nullable=True),
        sa.Column("port_kind", sa.String(length=16), nullable=False),
        sa.Column("probed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok','fail','timeout','error')",
            name="ck_dp_availability_probes_status",
        ),
    )
    op.create_index(
        "ix_dp_availability_probes_product",
        "data_product_availability_probes",
        ["data_product_id", "probed_at"],
    )

    op.create_table(
        "data_product_query_perf_samples",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("table_name", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.CheckConstraint(
            "status IN ('ok','fail','timeout')",
            name="ck_dp_query_perf_status",
        ),
    )
    op.create_index(
        "ix_dp_query_perf_product",
        "data_product_query_perf_samples",
        ["data_product_id", "started_at"],
    )


def downgrade() -> None:
    """Drop the columns + tables added above."""
    op.drop_index(
        "ix_dp_query_perf_product",
        table_name="data_product_query_perf_samples",
    )
    op.drop_table("data_product_query_perf_samples")
    op.drop_index(
        "ix_dp_availability_probes_product",
        table_name="data_product_availability_probes",
    )
    op.drop_table("data_product_availability_probes")
    op.drop_column("data_product_slos", "last_measurement_detail_json")
    op.drop_column("data_product_slos", "last_measured_at")
