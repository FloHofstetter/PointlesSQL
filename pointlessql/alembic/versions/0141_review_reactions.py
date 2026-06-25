"""review reactions table

Adds ``data_product_review_reactions`` — emoji reactions on a review,
mirroring ``data_product_comment_reactions``.  Reviews of one product
all share that product's social anchor, so reactions key on the
``review_id`` PK; otherwise every sibling review of the same product
would share a single count.  One row per ``(review, user, emoji)``.

Revision ID: 0141
Revises: 0140
Create Date: 2026-06-02 13:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0141"
down_revision: str | None = "0140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create data_product_review_reactions + its lookup indexes."""
    op.create_table(
        "data_product_review_reactions",
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("social_target_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["data_product_reviews.id"],
            name="fk_dp_review_reactions_review",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_dp_review_reactions_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["social_target_id"],
            ["social_targets.id"],
            name="fk_dp_review_reactions_target",
        ),
        sa.PrimaryKeyConstraint(
            "review_id",
            "user_id",
            "emoji",
            name="pk_dp_review_reactions",
        ),
    )
    op.create_index(
        "ix_dp_review_reactions_review",
        "data_product_review_reactions",
        ["review_id"],
    )
    op.create_index(
        "ix_data_product_review_reactions_social_target",
        "data_product_review_reactions",
        ["social_target_id"],
    )


def downgrade() -> None:
    """Drop data_product_review_reactions and its indexes."""
    op.drop_index(
        "ix_data_product_review_reactions_social_target",
        table_name="data_product_review_reactions",
    )
    op.drop_index(
        "ix_dp_review_reactions_review",
        table_name="data_product_review_reactions",
    )
    op.drop_table("data_product_review_reactions")
