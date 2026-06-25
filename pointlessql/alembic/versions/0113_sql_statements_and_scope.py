"""external SQL Statement Execution API state

Two schema changes:

1. ``api_keys.sql_execute`` BOOLEAN NOT NULL DEFAULT FALSE — new
   scope flag gating the public DBX-compatible SQL Statement
   Execution API.  Independent of every other scope.
2. ``sql_statements`` — new table storing the lifecycle of each
   ``POST /api/2.0/sql/statements`` submission (PENDING → RUNNING →
   SUCCEEDED / FAILED / CANCELED) and the gzipped DBX envelope so
   poll / chunk-fetch routes can stream back without re-serialising.

No backfill needed — every existing key keeps zero scopes here
because external SQL submission is a new surface; admins must
explicitly flip ``sql_execute=True`` to grant access.

Revision ID: 0113
Revises: 0112
Create Date: 2026-05-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0113"
down_revision: str | None = "0112"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add scope column + create statement-store table."""
    op.add_column(
        "api_keys",
        sa.Column(
            "sql_execute",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_table(
        "sql_statements",
        sa.Column("statement_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id"),
            nullable=False,
        ),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("statement_text", sa.Text(), nullable=False),
        sa.Column("catalog", sa.String(length=255), nullable=True),
        sa.Column("schema_name", sa.String(length=255), nullable=True),
        sa.Column("row_limit", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_payload", sa.LargeBinary(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_sql_statements_submitted_at", "sql_statements", ["submitted_at"])
    op.create_index("ix_sql_statements_status", "sql_statements", ["status"])
    op.create_index("ix_sql_statements_api_key_id", "sql_statements", ["api_key_id"])


def downgrade() -> None:
    """Drop statement-store table + scope column."""
    op.drop_index("ix_sql_statements_api_key_id", table_name="sql_statements")
    op.drop_index("ix_sql_statements_status", table_name="sql_statements")
    op.drop_index("ix_sql_statements_submitted_at", table_name="sql_statements")
    op.drop_table("sql_statements")
    op.drop_column("api_keys", "sql_execute")
