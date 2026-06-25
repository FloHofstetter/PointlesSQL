"""interoperability + mesh observability

Three new tables + one column for the mesh plane:

- ``data_product_slos`` — declared service-level objectives per product
  (the full SLO set beyond freshness).  CASCADE on ``data_products.id``.
- ``mesh_entities`` — polysemic business entities shared across the mesh
  (one per workspace).  FK on ``workspaces.id``.
- ``mesh_entity_bindings`` — binds an entity to one UC column inside a
  product.  CASCADE on ``mesh_entities.id`` + ``data_products.id``.
- ``agent_run_operations.correlation_id`` — cross-product trace id so a
  multi-product task can be reassembled into one timeline.

No data migration: existing products carry no SLOs / entity bindings and
existing operation rows have a NULL correlation id, so behaviour is
unchanged until an owner declares them.

Revision ID: 0120
Revises: 0119
Create Date: 2026-05-29 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0120"
down_revision: str | None = "0119"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the SLO + mesh tables and add the correlation column."""
    op.create_table(
        "data_product_slos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=255), nullable=True),
        sa.Column("slo_kind", sa.String(length=24), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("comparator", sa.String(length=4), nullable=False, server_default="lte"),
        sa.Column("unit", sa.String(length=24), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "data_product_id",
            "table_name",
            "slo_kind",
            name="uq_dp_slos_identity",
        ),
        sa.CheckConstraint(
            "slo_kind IN ('freshness','timeliness','completeness','volume',"
            "'statistical_shape','lineage','precision_accuracy','availability',"
            "'performance')",
            name="ck_dp_slos_kind",
        ),
        sa.CheckConstraint(
            "comparator IN ('lte','gte','eq')",
            name="ck_dp_slos_comparator",
        ),
    )
    op.create_index("ix_dp_slos_product", "data_product_slos", ["data_product_id"])

    op.create_table(
        "mesh_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_mesh_entities_ws_slug"),
    )
    op.create_index("ix_mesh_entities_workspace", "mesh_entities", ["workspace_id"])

    op.create_table(
        "mesh_entity_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "mesh_entity_id",
            sa.Integer(),
            sa.ForeignKey("mesh_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("catalog", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "mesh_entity_id",
            "data_product_id",
            "table_name",
            "column_name",
            name="uq_mesh_binding_identity",
        ),
    )
    op.create_index("ix_mesh_binding_entity", "mesh_entity_bindings", ["mesh_entity_id"])
    op.create_index("ix_mesh_binding_product", "mesh_entity_bindings", ["data_product_id"])
    op.create_index(
        "ix_mesh_binding_column",
        "mesh_entity_bindings",
        ["catalog", "schema_name", "table_name", "column_name"],
    )

    with op.batch_alter_table("agent_run_operations") as batch:
        batch.add_column(sa.Column("correlation_id", sa.String(length=64), nullable=True))
        batch.create_index("ix_agent_run_operations_correlation", ["correlation_id"])


def downgrade() -> None:
    """Drop the SLO + mesh tables and the correlation column."""
    with op.batch_alter_table("agent_run_operations") as batch:
        batch.drop_index("ix_agent_run_operations_correlation")
        batch.drop_column("correlation_id")

    op.drop_index("ix_mesh_binding_column", table_name="mesh_entity_bindings")
    op.drop_index("ix_mesh_binding_product", table_name="mesh_entity_bindings")
    op.drop_index("ix_mesh_binding_entity", table_name="mesh_entity_bindings")
    op.drop_table("mesh_entity_bindings")

    op.drop_index("ix_mesh_entities_workspace", table_name="mesh_entities")
    op.drop_table("mesh_entities")

    op.drop_index("ix_dp_slos_product", table_name="data_product_slos")
    op.drop_table("data_product_slos")
