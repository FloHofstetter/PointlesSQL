"""cost-attribution + quotas + mesh-health dashboard

Two new ledgers + three policy columns enable per-product / per-
consumer cost attribution plus 429-style quota enforcement:

* ``data_product_query_cost`` — raw per-query rows the meter writes
  after every PQL read.  Columns carry cost (Numeric), bytes
  scanned + rows returned (BigInt), table list (JSON), authoring +
  consumer product/user attribution, query kind, error class.
* ``data_product_cost_buckets_hourly`` — hourly rollup the
  scheduler computes from the raw ledger.  UNIQUE(bucket_hour,
  data_product, consumer_user) keeps idempotency on re-runs.
* ``data_product_policies.max_cost_per_day`` +
  ``max_queries_per_hour`` + ``quota_enforcement`` (CHECK in
  off/warn/strict) plus the same trio on
  ``workspace_governance_policies``.  Workspace policy values are
  NOT NULL with defaults (off / NULL / NULL); product overrides
  are NULL-able.

Revision ID: 0135
Revises: 0134
Create Date: 2026-05-30 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0135"
down_revision: str | None = "0134"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the cost-ledger tables + quota columns."""
    op.create_table(
        "data_product_query_cost",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "estimated_cost",
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("bytes_scanned", sa.BigInteger(), nullable=True),
        sa.Column("rows_returned", sa.BigInteger(), nullable=True),
        sa.Column("table_list_json", sa.Text(), nullable=True),
        sa.Column(
            "principal_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id"),
            nullable=True,
        ),
        sa.Column(
            "authoring_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "consumer_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query_kind", sa.String(length=24), nullable=False, server_default="select"),
        sa.Column("error_class", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_dp_query_cost_started",
        "data_product_query_cost",
        ["started_at"],
    )
    op.create_index(
        "ix_dp_query_cost_product",
        "data_product_query_cost",
        ["authoring_product_id", "started_at"],
    )
    op.create_index(
        "ix_dp_query_cost_consumer",
        "data_product_query_cost",
        ["principal_user_id", "started_at"],
    )

    op.create_table(
        "data_product_cost_buckets_hourly",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bucket_hour", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "consumer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("query_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "total_estimated_cost",
            sa.Numeric(precision=14, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_bytes_scanned",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint(
            "bucket_hour",
            "data_product_id",
            "consumer_user_id",
            name="uq_dp_cost_buckets_hourly_triple",
        ),
    )
    op.create_index(
        "ix_dp_cost_buckets_hour",
        "data_product_cost_buckets_hourly",
        ["bucket_hour"],
    )

    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.add_column(
            sa.Column(
                "max_cost_per_day",
                sa.Numeric(precision=10, scale=2),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("max_queries_per_hour", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "quota_enforcement",
                sa.String(length=8),
                nullable=False,
                server_default="off",
            )
        )
        batch.create_check_constraint(
            "ck_workspace_governance_policies_quota_enforcement",
            "quota_enforcement IN ('off','warn','strict')",
        )

    with op.batch_alter_table("data_product_policies") as batch:
        batch.add_column(
            sa.Column(
                "max_cost_per_day",
                sa.Numeric(precision=10, scale=2),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("max_queries_per_hour", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("quota_enforcement", sa.String(length=8), nullable=True))
        batch.create_check_constraint(
            "ck_data_product_policies_quota_enforcement",
            "quota_enforcement IS NULL OR quota_enforcement IN ('off','warn','strict')",
        )


def downgrade() -> None:
    """Drop the cost ledger + quota columns."""
    with op.batch_alter_table("data_product_policies") as batch:
        batch.drop_constraint("ck_data_product_policies_quota_enforcement", type_="check")
        batch.drop_column("quota_enforcement")
        batch.drop_column("max_queries_per_hour")
        batch.drop_column("max_cost_per_day")
    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.drop_constraint("ck_workspace_governance_policies_quota_enforcement", type_="check")
        batch.drop_column("quota_enforcement")
        batch.drop_column("max_queries_per_hour")
        batch.drop_column("max_cost_per_day")
    op.drop_index(
        "ix_dp_cost_buckets_hour",
        table_name="data_product_cost_buckets_hourly",
    )
    op.drop_table("data_product_cost_buckets_hourly")
    op.drop_index("ix_dp_query_cost_consumer", table_name="data_product_query_cost")
    op.drop_index("ix_dp_query_cost_product", table_name="data_product_query_cost")
    op.drop_index("ix_dp_query_cost_started", table_name="data_product_query_cost")
    op.drop_table("data_product_query_cost")
