"""data product endorsements (Phase 72.4)

Adds the ``data_product_endorsements`` table with the four
typed states enforced by a CHECK constraint.  Active rows have
``removed_at IS NULL``; the composite UNIQUE on
``(workspace_id, data_product_id, endorsement_type, removed_at)``
allows re-applying after a removal.

Revision ID: g3i5k7m9o1q3
Revises: f2h4j6l8n0p2
Create Date: 2026-05-13 00:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g3i5k7m9o1q3"
down_revision: str | None = "f2h4j6l8n0p2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``data_product_endorsements``."""
    op.create_table(
        "data_product_endorsements",
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
        sa.Column("endorsement_type", sa.Text(), nullable=False),
        sa.Column(
            "applied_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note_md", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "workspace_id",
            "data_product_id",
            "endorsement_type",
            "removed_at",
            name="uq_dp_endorsement_active",
        ),
        sa.CheckConstraint(
            "endorsement_type IN ('verified-by-steward', 'production-ready', "
            "'deprecated', 'under-review')",
            name="ck_dp_endorsement_type",
        ),
    )
    op.create_index(
        "ix_dp_endorsement_dp_type",
        "data_product_endorsements",
        ["data_product_id", "endorsement_type"],
    )


def downgrade() -> None:
    """Drop ``data_product_endorsements``."""
    op.drop_index("ix_dp_endorsement_dp_type", table_name="data_product_endorsements")
    op.drop_table("data_product_endorsements")
