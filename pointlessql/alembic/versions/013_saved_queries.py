"""Sprint 51: saved_queries.

Revision ID: 013
Revises: 012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``saved_queries`` + the owner+updated index.

    The slug carries a uniqueness constraint so the editor's
    drawer can link by ``/api/saved-queries/<slug>`` without
    client-side disambiguation.  ``is_shared`` defaults to
    ``False`` so "save" is a private default.
    """
    op.create_table(
        "saved_queries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=200), nullable=False, unique=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("sql_text", sa.Text, nullable=False),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "is_shared",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_saved_queries_owner_updated",
        "saved_queries",
        ["owner_id", "updated_at"],
    )


def downgrade() -> None:
    """Drop the Sprint 51 saved-queries surface."""
    op.drop_index("ix_saved_queries_owner_updated", table_name="saved_queries")
    op.drop_table("saved_queries")
