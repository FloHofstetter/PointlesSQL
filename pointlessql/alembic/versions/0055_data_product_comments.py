"""data product comments

Adds the ``data_product_comments`` table backing the Discussion
tab on the data-product detail page.  Threaded via
``parent_comment_id`` (self-FK), workspace-scoped, soft-deleted
via ``deleted_at`` so the audit trail stays coherent.

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-12 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_comments`` with two indexes."""
    op.create_table(
        "data_product_comments",
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
            "parent_comment_id",
            sa.Integer(),
            sa.ForeignKey("data_product_comments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column(
            "mentioned_user_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dp_comments_dp_created",
        "data_product_comments",
        ["data_product_id", "created_at"],
    )
    op.create_index(
        "ix_dp_comments_parent",
        "data_product_comments",
        ["parent_comment_id"],
    )


def downgrade() -> None:
    """Drop ``data_product_comments`` and its indexes."""
    op.drop_index("ix_dp_comments_parent", table_name="data_product_comments")
    op.drop_index("ix_dp_comments_dp_created", table_name="data_product_comments")
    op.drop_table("data_product_comments")
