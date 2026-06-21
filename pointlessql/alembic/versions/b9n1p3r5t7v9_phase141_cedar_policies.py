"""phase 141: cedar policy-as-code modules + decision ledger

Introduces the persistence the Cedar policy-engine needs:

* ``policy_modules`` — authored, versioned Cedar source.  One row per
  module, scoped to a workspace.  Linking happens via the new JSON
  column on the existing policy rows.
* ``policy_module_decisions`` — per-evaluation ledger.  Each row is
  one Cedar ``is_authorized`` call, kept for the decision-log surface
  and for post-hoc compliance review.
* ``data_product_policies.linked_policy_module_ids`` +
  ``workspace_governance_policies.linked_policy_module_ids`` — JSON
  array of module ids active on the product / workspace.

Revision ID: b9n1p3r5t7v9
Revises: z7l9n1p3r5t7
Create Date: 2026-05-30 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9n1p3r5t7v9"
down_revision: str | None = "z7l9n1p3r5t7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create policy-module tables + extend policy rows with link column."""
    op.create_table(
        "policy_modules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("cedar_source", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_policy_modules_ws_name"),
    )
    op.create_index(
        "ix_policy_modules_ws",
        "policy_modules",
        ["workspace_id", "enabled"],
    )

    op.create_table(
        "policy_module_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "policy_module_id",
            sa.Integer(),
            sa.ForeignKey("policy_modules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "principal_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "effect IN ('permit','forbid')",
            name="ck_policy_module_decisions_effect",
        ),
    )
    op.create_index(
        "ix_policy_module_decisions_module",
        "policy_module_decisions",
        ["policy_module_id", "decision_at"],
    )
    op.create_index(
        "ix_policy_module_decisions_principal",
        "policy_module_decisions",
        ["principal_user_id", "decision_at"],
    )

    op.add_column(
        "workspace_governance_policies",
        sa.Column("linked_policy_module_ids", sa.Text(), nullable=True),
    )
    op.add_column(
        "data_product_policies",
        sa.Column("linked_policy_module_ids", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Reverse 141 — drop the columns, decisions ledger, and modules."""
    op.drop_column("data_product_policies", "linked_policy_module_ids")
    op.drop_column("workspace_governance_policies", "linked_policy_module_ids")
    op.drop_index(
        "ix_policy_module_decisions_principal",
        table_name="policy_module_decisions",
    )
    op.drop_index(
        "ix_policy_module_decisions_module",
        table_name="policy_module_decisions",
    )
    op.drop_table("policy_module_decisions")
    op.drop_index("ix_policy_modules_ws", table_name="policy_modules")
    op.drop_table("policy_modules")
