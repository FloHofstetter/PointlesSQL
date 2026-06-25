"""data product readme

Adds the ``data_product_readmes`` table backing the README tab on
the data-product detail page.  One row per *version*; latest =
``max(version_int)`` per ``(workspace_id, data_product_id)``.

Revision ID: 0059
Revises: 0058
Create Date: 2026-05-12 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_readmes`` with UNIQUE + index."""
    op.create_table(
        "data_product_readmes",
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
        sa.Column("version_int", sa.Integer(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "version_int",
            name="uq_dp_readme_versioned",
        ),
    )
    op.create_index(
        "ix_dp_readme_dp_version",
        "data_product_readmes",
        ["data_product_id", "version_int"],
    )


def downgrade() -> None:
    """Drop ``data_product_readmes`` and its index."""
    op.drop_index("ix_dp_readme_dp_version", table_name="data_product_readmes")
    op.drop_table("data_product_readmes")
