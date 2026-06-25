"""data_products + data_product_contract_events for native Data-Product support

Phase 50.1 introduces the data-product convention: a UC schema can
opt into product status by shipping a ``pointlessql.yaml`` file in
the data team's repo.  The yaml is canonical (git-blame is the
audit log); these two tables cache the parsed contract and log
every contract validation against agent-run operations.

Two tables, one migration:

* ``data_products`` — one row per ``(workspace, catalog, schema)``
  declared as a product.  The pydantic-validated contract is
  stored as JSON so the diff helper, enforcement hook, and plugin
  tools can read it without touching the filesystem.
* ``data_product_contract_events`` — append-only log: one row per
  ``pql.write`` / ``pql.merge`` against a product-bearing schema.
  Outcome is one of ``compliant`` / ``schema_drift_warning`` /
  ``violated`` / ``no_contract``.

Storage decision: PointlesSQL metadata DB (small registry, scoped
per workspace, no external credentials).  The ``contract_yaml_hash``
column lets the loader detect drift between the cached row and a
freshly-loaded yaml.

Revision ID: 0045
Revises: 0044
Create Date: 2026-05-07 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create data_products + data_product_contract_events."""
    op.create_table(
        "data_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("catalog_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column(
            "steward_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sla_minutes", sa.Integer(), nullable=True),
        sa.Column("contract_yaml_hash", sa.String(length=64), nullable=False),
        sa.Column("contract_json", sa.Text(), nullable=False),
        sa.Column("last_loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "catalog_name",
            "schema_name",
            name="uq_data_products_ws_catalog_schema",
        ),
    )
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.create_index(
            "ix_data_products_workspace_loaded",
            ["workspace_id", "last_loaded_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_data_products_steward",
            ["steward_user_id"],
            unique=False,
        )

    op.create_table(
        "data_product_contract_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "agent_run_operation_id",
            sa.Integer(),
            sa.ForeignKey("agent_run_operations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "outcome IN ('compliant','schema_drift_warning','violated','no_contract')",
            name="ck_data_product_contract_events_outcome",
        ),
    )
    with op.batch_alter_table("data_product_contract_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_data_product_contract_events_product_created",
            ["data_product_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_data_product_contract_events_op",
            ["agent_run_operation_id"],
            unique=False,
        )


def downgrade() -> None:
    """Drop data_product_contract_events + data_products."""
    with op.batch_alter_table("data_product_contract_events", schema=None) as batch_op:
        batch_op.drop_index("ix_data_product_contract_events_op")
        batch_op.drop_index("ix_data_product_contract_events_product_created")
    op.drop_table("data_product_contract_events")
    with op.batch_alter_table("data_products", schema=None) as batch_op:
        batch_op.drop_index("ix_data_products_steward")
        batch_op.drop_index("ix_data_products_workspace_loaded")
    op.drop_table("data_products")
