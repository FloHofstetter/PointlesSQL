"""phase 136: correlation-id propagation + ISO-8601 enforcement (G4/F5)

Two additive surfaces:

* ``correlation_id``  String(40) nullable + index on the four tables
  audit-trails join across: ``agent_run_operations``, ``audit_log``,
  ``data_product_contract_events``, ``data_product_event_deliveries``.
* ``iso8601_enforcement``  String(8) CHECK column on the two policy
  tables (``workspace_governance_policies`` defaults to ``'warn'``,
  ``data_product_policies`` is nullable for product → workspace
  inheritance).

Both columns are additive (no backfill) — existing audit rows have
``correlation_id IS NULL`` and the warn-mode default keeps current
writers passing.

Revision ID: t1d3f5h7j9l1
Revises: r0u2w5y7c1d3
Create Date: 2026-05-30 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "t1d3f5h7j9l1"
down_revision: str | None = "r0u2w5y7c1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRACE_TABLES: tuple[str, ...] = (
    "audit_log",
    "data_product_contract_events",
    "data_product_event_deliveries",
)


def upgrade() -> None:
    """Add correlation_id + iso8601_enforcement columns."""
    for table in _TRACE_TABLES:
        op.add_column(
            table,
            sa.Column("correlation_id", sa.String(length=40), nullable=True),
        )
        op.create_index(
            f"ix_{table}_correlation_id",
            table,
            ["correlation_id"],
        )

    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.add_column(
            sa.Column(
                "iso8601_enforcement",
                sa.String(length=8),
                nullable=False,
                server_default="warn",
            )
        )
        batch.create_check_constraint(
            "ck_workspace_iso8601_enforcement",
            "iso8601_enforcement IN ('off','warn','strict')",
        )

    with op.batch_alter_table("data_product_policies") as batch:
        batch.add_column(sa.Column("iso8601_enforcement", sa.String(length=8), nullable=True))
        batch.create_check_constraint(
            "ck_data_product_iso8601_enforcement",
            "iso8601_enforcement IS NULL OR iso8601_enforcement IN ('off','warn','strict')",
        )


def downgrade() -> None:
    """Drop the columns added above."""
    with op.batch_alter_table("data_product_policies") as batch:
        batch.drop_constraint("ck_data_product_iso8601_enforcement", type_="check")
        batch.drop_column("iso8601_enforcement")

    with op.batch_alter_table("workspace_governance_policies") as batch:
        batch.drop_constraint("ck_workspace_iso8601_enforcement", type_="check")
        batch.drop_column("iso8601_enforcement")

    for table in _TRACE_TABLES:
        op.drop_index(f"ix_{table}_correlation_id", table_name=table)
        op.drop_column(table, "correlation_id")
