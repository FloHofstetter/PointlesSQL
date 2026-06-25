"""computational governance policy-as-code

Four new tables for per-product policy-as-code + the control-port:

- ``workspace_governance_policies`` — workspace-wide default policy
  (retention / encryption-class / residency / consent).  One row per
  workspace; products inherit unless they override.
- ``data_product_policies`` — per-product override of the policy
  fields.  CASCADE on ``data_products.id``; unique per product.
- ``data_product_column_classifications`` — confidentiality class of a
  UC column, driving read-time masking.  CASCADE on
  ``data_products.id``.
- ``data_product_forget_requests`` — right-to-be-forgotten ledger
  (subject value stored hashed).  CASCADE on ``data_products.id``;
  SET NULL on ``agent_runs.id``.

No data migration: existing products inherit "unset" policy + carry no
classifications, so behaviour is unchanged until an owner declares
governance.

Revision ID: 0119
Revises: 0118
Create Date: 2026-05-29 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0119"
down_revision: str | None = "0118"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the 4 governance tables."""
    op.create_table(
        "workspace_governance_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("encryption_class", sa.String(length=16), nullable=True),
        sa.Column("residency_region", sa.String(length=64), nullable=True),
        sa.Column(
            "consent_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("consent_basis", sa.String(length=200), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_governance_policies_ws"),
        sa.CheckConstraint(
            "encryption_class IS NULL OR "
            "encryption_class IN ('none','at_rest','in_transit','full')",
            name="ck_workspace_governance_policies_encryption",
        ),
    )

    op.create_table(
        "data_product_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("encryption_class", sa.String(length=16), nullable=True),
        sa.Column("residency_region", sa.String(length=64), nullable=True),
        sa.Column("consent_required", sa.Boolean(), nullable=True),
        sa.Column("consent_basis", sa.String(length=200), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", name="uq_data_product_policies_product"),
        sa.CheckConstraint(
            "encryption_class IS NULL OR "
            "encryption_class IN ('none','at_rest','in_transit','full')",
            name="ck_data_product_policies_encryption",
        ),
    )

    op.create_table(
        "data_product_column_classifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
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
        sa.Column("classification", sa.String(length=16), nullable=False),
        sa.Column("masking_strategy", sa.String(length=16), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "data_product_id",
            "catalog",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_dp_classifications_identity",
        ),
        sa.CheckConstraint(
            "classification IN ('public','internal','confidential','pii','phi')",
            name="ck_dp_classifications_class",
        ),
        sa.CheckConstraint(
            "masking_strategy IS NULL OR "
            "masking_strategy IN ('none','hash','partial','full','null')",
            name="ck_dp_classifications_strategy",
        ),
    )
    op.create_index(
        "ix_dp_classifications_lookup",
        "data_product_column_classifications",
        ["catalog", "schema_name", "table_name", "column_name"],
    )
    op.create_index(
        "ix_dp_classifications_product",
        "data_product_column_classifications",
        ["data_product_id"],
    )

    op.create_table(
        "data_product_forget_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_column", sa.String(length=255), nullable=False),
        sa.Column("subject_value_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="proposed",
        ),
        sa.Column("tables_affected_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("rows_deleted", sa.Integer(), nullable=True),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "executed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed','executed','rejected')",
            name="ck_dp_forget_status",
        ),
    )
    op.create_index(
        "ix_dp_forget_product",
        "data_product_forget_requests",
        ["data_product_id"],
    )


def downgrade() -> None:
    """Drop the 4 governance tables."""
    op.drop_index("ix_dp_forget_product", table_name="data_product_forget_requests")
    op.drop_table("data_product_forget_requests")

    op.drop_index(
        "ix_dp_classifications_product",
        table_name="data_product_column_classifications",
    )
    op.drop_index(
        "ix_dp_classifications_lookup",
        table_name="data_product_column_classifications",
    )
    op.drop_table("data_product_column_classifications")

    op.drop_table("data_product_policies")
    op.drop_table("workspace_governance_policies")
