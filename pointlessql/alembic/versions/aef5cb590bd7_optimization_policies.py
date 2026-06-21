"""optimization_policies

Adds the predictive-optimization control registry: one row per catalog /
schema / table scope declaring which autonomous Delta maintenance
operations (OPTIMIZE, VACUUM, ANALYZE) should run, resolved
most-specific-first.  The engine that performs the maintenance is the
existing PQL / deltalake path; these rows are control metadata only.

Revision ID: aef5cb590bd7
Revises: ca59a629d146
Create Date: 2026-06-20 23:51:43.018345
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aef5cb590bd7"
down_revision: str | None = "ca59a629d146"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``optimization_policies`` registry table + index."""
    op.create_table(
        "optimization_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_value", sa.String(length=768), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("optimize", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("vacuum", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("analyze", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("vacuum_retention_hours", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('catalog', 'schema', 'table')",
            name="ck_optimization_policies_scope_type",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "scope_type", "scope_value", name="uq_optimization_policies_scope"
        ),
    )
    with op.batch_alter_table("optimization_policies", schema=None) as batch_op:
        batch_op.create_index("ix_optimization_policies_workspace", ["workspace_id"], unique=False)


def downgrade() -> None:
    """Drop the ``optimization_policies`` table."""
    with op.batch_alter_table("optimization_policies", schema=None) as batch_op:
        batch_op.drop_index("ix_optimization_policies_workspace")
    op.drop_table("optimization_policies")
