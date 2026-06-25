"""data product reviews

Adds the ``data_product_reviews`` table backing the Reviews tab on
the data-product detail page.  One row per ``(workspace_id,
data_product_id, author_user_id)`` triple (unique constraint).
Stars are constrained to 1..5 at the DB layer so a buggy client
can't slip a 0 or 6 past us.

Revision ID: 0056
Revises: 0055
Create Date: 2026-05-12 16:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_reviews`` with unique + CHECK + index."""
    op.create_table(
        "data_product_reviews",
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
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("dp_version_at_review", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "author_user_id",
            name="uq_dp_review_one_per_user",
        ),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_dp_review_stars_range"),
    )
    op.create_index(
        "ix_dp_reviews_dp_stars",
        "data_product_reviews",
        ["data_product_id", "stars"],
    )


def downgrade() -> None:
    """Drop ``data_product_reviews`` and its index."""
    op.drop_index("ix_dp_reviews_dp_stars", table_name="data_product_reviews")
    op.drop_table("data_product_reviews")
