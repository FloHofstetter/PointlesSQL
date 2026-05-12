"""data product follows (Phase 71.3)

Adds the ``data_product_follows`` composite-PK table backing the
Follow / Subscribe button on the data-product detail page and the
``/data-products/followed`` per-user index.

Revision ID: c9e1g3i5k7m9
Revises: b8d0f2h4j6m8
Create Date: 2026-05-12 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1g3i5k7m9"
down_revision: str | None = "b8d0f2h4j6m8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_follows`` with composite PK + index."""
    op.create_table(
        "data_product_follows",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            primary_key=True,
            server_default="1",
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dp_follows_user",
        "data_product_follows",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Drop ``data_product_follows`` and its index."""
    op.drop_index("ix_dp_follows_user", table_name="data_product_follows")
    op.drop_table("data_product_follows")
