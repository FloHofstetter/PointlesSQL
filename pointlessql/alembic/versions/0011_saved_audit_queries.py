"""saved_audit_queries table + 5 starter rows

 (Audit Cockpit) adds a separate "saved query" surface
scoped to the audit tables.  See
``pointlessql/models/saved_audit_queries.py`` for the column
contract; this migration creates the table and seeds the starter
rows the cockpit lists by default.

Starter rows live with ``is_starter=True`` and ``owner_id=NULL``
so they survive any user deletion.  PATCH and DELETE refuse on
those rows at the service layer (no DB-level enforcement — the
column is the source of truth).

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-28 18:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saved_audit_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_starter", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("alert_threshold_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug"),
    )
    with op.batch_alter_table("saved_audit_queries", schema=None) as batch_op:
        batch_op.create_index(
            "ix_saved_audit_queries_owner_updated",
            ["owner_id", "updated_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_saved_audit_queries_starter",
            ["is_starter"],
            unique=False,
        )
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    from pointlessql.models.starter_audit_queries import starter_rows

    rows_in = starter_rows(op.get_bind().dialect.name)
    for r in rows_in:
        row: dict[str, object] = dict(r)
        row.update(
            {
                "owner_id": None,
                "is_shared": True,
                "is_starter": True,
                "alert_threshold_count": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        rows.append(row)
    op.bulk_insert(
        sa.table(
            "saved_audit_queries",
            sa.column("slug", sa.String),
            sa.column("title", sa.String),
            sa.column("description", sa.String),
            sa.column("sql_text", sa.Text),
            sa.column("owner_id", sa.Integer),
            sa.column("is_shared", sa.Boolean),
            sa.column("is_starter", sa.Boolean),
            sa.column("alert_threshold_count", sa.Integer),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        rows,
    )


def downgrade() -> None:
    with op.batch_alter_table("saved_audit_queries", schema=None) as batch_op:
        batch_op.drop_index("ix_saved_audit_queries_starter")
        batch_op.drop_index("ix_saved_audit_queries_owner_updated")
    op.drop_table("saved_audit_queries")
