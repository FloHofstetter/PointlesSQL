"""data product passports

Adds the ``data_product_passports`` table backing the auto-
generated markdown briefing per DP.  Distinct from
``data_product_readmes`` (which is steward-authored).

Revision ID: 0064
Revises: 0063
Create Date: 2026-05-14 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_passports``."""
    op.create_table(
        "data_product_passports",
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
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("source_tables_json", sa.Text(), nullable=False),
        sa.Column("downstream_tables_json", sa.Text(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_trigger", sa.String(length=20), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "version_int",
            name="uq_dp_passport_version",
        ),
        sa.CheckConstraint(
            "refresh_trigger IN ('schema_changed', 'manual', 'periodic')",
            name="ck_dp_passport_trigger",
        ),
    )
    op.create_index(
        "ix_dp_passport_dp_v",
        "data_product_passports",
        ["data_product_id", "version_int"],
    )


def downgrade() -> None:
    """Drop ``data_product_passports``."""
    op.drop_index("ix_dp_passport_dp_v", table_name="data_product_passports")
    op.drop_table("data_product_passports")
