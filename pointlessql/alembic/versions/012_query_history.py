"""Sprint 50: query_history + query_history_tables.

Revision ID: 012
Revises: 011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the two new tables plus the forward + reverse indexes.

    ``query_history`` holds one row per ``POST /api/sql/execute`` call
    (success OR failure).  ``query_history_tables`` is a thin join
    populated from the sqlglot parse of the SQL so the "who queried
    table X" reverse lookup can be cheap.
    """
    op.create_table(
        "query_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("user_email", sa.String(length=254), nullable=False),
        sa.Column("sql_text", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_query_history_user_started",
        "query_history",
        ["user_id", "started_at"],
    )
    op.create_index(
        "ix_query_history_started",
        "query_history",
        ["started_at"],
    )

    op.create_table(
        "query_history_tables",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "query_history_id",
            sa.Integer,
            sa.ForeignKey("query_history.id"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(length=500), nullable=False),
        sa.Column(
            "access_type",
            sa.String(length=10),
            nullable=False,
            server_default="read",
        ),
    )
    op.create_index(
        "ix_query_history_tables_full_name",
        "query_history_tables",
        ["full_name", "query_history_id"],
    )


def downgrade() -> None:
    """Drop the Sprint 50 history surface, indexes first."""
    op.drop_index("ix_query_history_tables_full_name", table_name="query_history_tables")
    op.drop_table("query_history_tables")
    op.drop_index("ix_query_history_started", table_name="query_history")
    op.drop_index("ix_query_history_user_started", table_name="query_history")
    op.drop_table("query_history")
