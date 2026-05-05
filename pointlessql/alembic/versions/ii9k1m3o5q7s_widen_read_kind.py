"""Widen ``query_history.read_kind`` from VARCHAR(20) to VARCHAR(32) (Sprint 32.0).

The column was introduced in Sprint 28.7 with ``String(20)``; subsequent
sprints added ``read_kind="audit_api_cross_workspace"`` (25 chars), which
silently passes on SQLite (varchar length is advisory there) but raises
``StringDataRightTruncation`` on Postgres.  Surfaced once Phase 31 made
the PG suite runnable end-to-end.

Revision ID: ii9k1m3o5q7s
Revises: hh8j0l2n4p6r
Create Date: 2026-05-05 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ii9k1m3o5q7s"
down_revision: str | None = "hh8j0l2n4p6r"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite treats VARCHAR length as advisory but the model uses
    # String(32), so ``alembic check`` flags drift if the DDL still
    # says VARCHAR(20).  Use batch_alter_table on SQLite (table
    # recreate, slow but correct) and a plain ALTER on PG.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "query_history",
            "read_kind",
            type_=sa.String(32),
            existing_nullable=False,
            existing_server_default="sql_execute",
        )
    else:
        with op.batch_alter_table("query_history", schema=None) as batch_op:
            batch_op.alter_column(
                "read_kind",
                type_=sa.String(32),
                existing_nullable=False,
                existing_server_default="sql_execute",
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "query_history",
            "read_kind",
            type_=sa.String(20),
            existing_nullable=False,
            existing_server_default="sql_execute",
        )
    else:
        with op.batch_alter_table("query_history", schema=None) as batch_op:
            batch_op.alter_column(
                "read_kind",
                type_=sa.String(20),
                existing_nullable=False,
                existing_server_default="sql_execute",
            )
