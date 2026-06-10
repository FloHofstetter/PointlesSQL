"""phase 131: bitemporal enforcement policy (F1/F5)

Adds one new table — ``data_product_bitemporal_policy`` — that lets a
steward override the workspace bitemporal defaults per-product:

- ``enforcement``                  ``off | opt_in | required`` (nullable
  inherit).
- ``processing_time_column``       Override column name (nullable).
- ``event_time_column``            Override column name (nullable).
- ``require_event_time``           Per-product require flag (nullable).

One row per product (unique on ``data_product_id``).  NULL fields
inherit the workspace-level :class:`BitemporalSettings`.  CASCADE on
``data_products.id`` so deleting a product removes its policy row.

Revision ID: m4o6q8s0u2w5
Revises: l3n5p7r9t1v3
Create Date: 2026-05-29 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m4o6q8s0u2w5"
down_revision: str | None = "l3n5p7r9t1v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``data_product_bitemporal_policy`` table."""
    op.create_table(
        "data_product_bitemporal_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enforcement", sa.String(length=16), nullable=True),
        sa.Column("processing_time_column", sa.String(length=120), nullable=True),
        sa.Column("event_time_column", sa.String(length=120), nullable=True),
        sa.Column("require_event_time", sa.Boolean(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", name="uq_dp_bitemporal_policy_product"),
        sa.CheckConstraint(
            "enforcement IS NULL OR enforcement IN ('off','opt_in','required')",
            name="ck_dp_bitemporal_policy_enforcement",
        ),
    )


def downgrade() -> None:
    """Drop the ``data_product_bitemporal_policy`` table."""
    op.drop_table("data_product_bitemporal_policy")
