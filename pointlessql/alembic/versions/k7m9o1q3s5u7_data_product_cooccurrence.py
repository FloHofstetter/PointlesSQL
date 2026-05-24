"""data product cooccurrence (Phase 73.5)

Adds the ``data_product_cooccurrence`` table backing the
cross-DP "agents who read X also read Y" recommendation
surface.

Revision ID: k7m9o1q3s5u7
Revises: j6l8n0p2r4t6
Create Date: 2026-05-14 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k7m9o1q3s5u7"
down_revision: str | None = "j6l8n0p2r4t6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_cooccurrence``."""
    op.create_table(
        "data_product_cooccurrence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "co_data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cooccurrence_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "co_data_product_id",
            "window_end",
            name="uq_dp_cooccurrence_pair",
        ),
        sa.CheckConstraint(
            "data_product_id != co_data_product_id",
            name="ck_dp_cooccurrence_distinct",
        ),
    )
    op.create_index(
        "ix_dp_cooccurrence_ws_dp",
        "data_product_cooccurrence",
        ["workspace_id", "data_product_id"],
    )


def downgrade() -> None:
    """Drop ``data_product_cooccurrence``."""
    op.drop_index("ix_dp_cooccurrence_ws_dp", table_name="data_product_cooccurrence")
    op.drop_table("data_product_cooccurrence")
