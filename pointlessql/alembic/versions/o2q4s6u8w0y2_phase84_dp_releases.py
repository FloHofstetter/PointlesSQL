"""Phase 84.2 — data_product_releases table.

One row per detected DataProduct version / hash bump.  Feeds the
DP detail page release stream + Atom feed.

Revision ID: o2q4s6u8w0y2
Revises: n1p3r5t7v9x1
Create Date: 2026-05-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "o2q4s6u8w0y2"
down_revision: str | None = "n1p3r5t7v9x1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_releases``."""
    op.create_table(
        "data_product_releases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("contract_yaml_hash", sa.String(length=64), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes_md", sa.Text(), nullable=True),
        sa.Column(
            "signed_off_by_email",
            sa.String(length=254),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_data_product_releases_dp_released",
        "data_product_releases",
        ["data_product_id", "released_at"],
    )


def downgrade() -> None:
    """Drop ``data_product_releases``."""
    op.drop_index(
        "ix_data_product_releases_dp_released",
        table_name="data_product_releases",
    )
    op.drop_table("data_product_releases")
