"""data product trending cache

Adds the ``data_product_trending`` cache table for the
``/data-products/trending`` page.  Refreshed by the
``_data_product_trending_loop`` background task every
``data_products.trending_refresh_interval_seconds``.

Revision ID: 0060
Revises: 0059
Create Date: 2026-05-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_trending`` with UNIQUE + index."""
    op.create_table(
        "data_product_trending",
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
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_run_count", sa.Integer(), nullable=False),
        sa.Column("write_count", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "window_end",
            name="uq_dp_trending_window",
        ),
    )
    op.create_index(
        "ix_dp_trending_workspace_window",
        "data_product_trending",
        ["workspace_id", "window_end"],
    )


def downgrade() -> None:
    """Drop ``data_product_trending`` and its index."""
    op.drop_index("ix_dp_trending_workspace_window", table_name="data_product_trending")
    op.drop_table("data_product_trending")
