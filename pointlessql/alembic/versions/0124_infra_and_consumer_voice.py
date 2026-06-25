"""infrastructure declarations + consumer-contributed metadata

Four new tables that round out the discovery surface with declarative
blocks the producer (infrastructure) and the consumers (use cases,
votes, ratings) can each populate.  No enforcement — these are pure
metadata so a consumer of the discovery URI can see "this product runs
on X, ratings ★4.3 across 21 users, top use case = Y".

Tables:

- ``data_product_infrastructure``       1:1 per product, steward-edited.
- ``data_product_use_cases``            1:N per product, any-user POST.
- ``data_product_use_case_votes``       1:1 per (use case, user).
- ``data_product_ratings``              1:1 per (product, user), upsert.

All four CASCADE on ``data_products.id``.

Revision ID: 0124
Revises: 0123
Create Date: 2026-05-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0124"
down_revision: str | None = "0123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four declarative-surface tables."""
    op.create_table(
        "data_product_infrastructure",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_class", sa.String(length=32), nullable=True),
        sa.Column("compute_runtime", sa.String(length=64), nullable=True),
        sa.Column("access_methods_json", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("data_product_id", name="uq_dp_infrastructure_product"),
        sa.CheckConstraint(
            "storage_class IS NULL OR storage_class IN ('delta','parquet','external')",
            name="ck_dp_infrastructure_storage_class",
        ),
    )

    op.create_table(
        "data_product_use_cases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "votes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dp_use_cases_product_votes",
        "data_product_use_cases",
        ["data_product_id", "votes"],
    )

    op.create_table(
        "data_product_use_case_votes",
        sa.Column(
            "use_case_id",
            sa.Integer(),
            sa.ForeignKey("data_product_use_cases.id", ondelete="CASCADE"),
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

    op.create_table(
        "data_product_ratings",
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
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_dp_ratings_score_range"),
    )


def downgrade() -> None:
    """Drop the four declarative-surface tables."""
    op.drop_table("data_product_ratings")
    op.drop_table("data_product_use_case_votes")
    op.drop_index("ix_dp_use_cases_product_votes", table_name="data_product_use_cases")
    op.drop_table("data_product_use_cases")
    op.drop_table("data_product_infrastructure")
