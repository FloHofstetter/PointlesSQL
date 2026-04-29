"""recent_tables (Sprint 17.5.1)

Server-side mirror of the Sprint-17.5 ``localStorage['pql.recentTables']``
block.  One row per ``(user, table_full_name)`` so the sidebar's
"Recent tables" list survives device + session changes.

Revision ID: p6l8n0q3s5u7
Revises: o5k7m9p2r4t6
Create Date: 2026-04-29 23:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p6l8n0q3s5u7"
down_revision: str | None = "o5k7m9p2r4t6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recent_tables",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("table_full_name", sa.String(length=512), nullable=False),
        sa.Column("last_visited_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id",
            "table_full_name",
            name="uq_recent_tables_user_table",
        ),
    )
    op.create_index(
        "ix_recent_tables_user_last_visited",
        "recent_tables",
        ["user_id", "last_visited_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recent_tables_user_last_visited", table_name="recent_tables")
    op.drop_table("recent_tables")
