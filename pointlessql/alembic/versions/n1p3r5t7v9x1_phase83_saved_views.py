"""Phase 83.1 — saved_views table.

One row per parameterised, SELECT-only view that a consumer can
run without touching the SQL editor.  Workspace-scoped,
owner-pinned.

Revision ID: n1p3r5t7v9x1
Revises: m0o2q4s6u8w0
Create Date: 2026-05-17 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n1p3r5t7v9x1"
down_revision: str | None = "m0o2q4s6u8w0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``saved_views`` + supporting indices."""
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column(
            "parameters_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "dp_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id"),
            nullable=True,
        ),
        sa.Column("target_fqn", sa.String(length=500), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_saved_views_slug"),
    )
    op.create_index(
        "ix_saved_views_workspace_active",
        "saved_views",
        ["workspace_id", "is_active"],
    )
    op.create_index("ix_saved_views_dp", "saved_views", ["dp_id"])
    op.create_index("ix_saved_views_target_fqn", "saved_views", ["target_fqn"])


def downgrade() -> None:
    """Drop ``saved_views`` + indices."""
    op.drop_index("ix_saved_views_target_fqn", table_name="saved_views")
    op.drop_index("ix_saved_views_dp", table_name="saved_views")
    op.drop_index("ix_saved_views_workspace_active", table_name="saved_views")
    op.drop_table("saved_views")
