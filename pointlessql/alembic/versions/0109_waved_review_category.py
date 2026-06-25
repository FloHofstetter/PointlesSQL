"""waved_review_category

Phase 101 Wave-D — add ``review`` to the comment-category CHECK so
notebook-cell reviews can persist under the existing polymorphic
comment surface.  The category column itself is unchanged; the
constraint just learns one extra value.

Revision ID: 0109
Revises: 0108
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace the four-value CHECK with a five-value one."""
    with op.batch_alter_table("data_product_comments") as batch:
        batch.drop_constraint("ck_dp_comment_category", type_="check")
        batch.create_check_constraint(
            "ck_dp_comment_category",
            "category IN ('general','question','announcement','idea','review')",
        )


def downgrade() -> None:
    """Restore the original four-value CHECK."""
    with op.batch_alter_table("data_product_comments") as batch:
        batch.drop_constraint("ck_dp_comment_category", type_="check")
        batch.create_check_constraint(
            "ck_dp_comment_category",
            "category IN ('general','question','announcement','idea')",
        )
