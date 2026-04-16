"""Create sync_run table.

Revision ID: 004
Revises: 003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the sync_run table for foreign-catalog sync history."""
    op.create_table(
        "sync_run",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("catalog_name", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("added_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("changed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dropped_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
    )
    # Index supports the "most recent N for this catalog" query used by
    # the history card; Postgres honours the DESC direction natively,
    # SQLite treats it as a hint but still uses the index.
    op.create_index(
        "ix_sync_run_catalog_started",
        "sync_run",
        ["catalog_name", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    """Drop the sync_run table."""
    op.drop_index("ix_sync_run_catalog_started", table_name="sync_run")
    op.drop_table("sync_run")
