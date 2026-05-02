"""lineage_row_rejects table for opt-in merge-reject capture

 surfaced one half of agent-debuggability: per-row provenance
chains that walk silver back to bronze.  The other half — visibility
into rows that were *supposed* to land but didn't — is filled by
this table.

``pql.merge(track_rejects=True)`` performs a pre-merge set-diff
between the source frame and the rows that actually merged into the
target, attaches an enumerated ``reason`` (NULL key, schema mismatch,
duplicate-in-source, predicate-excluded, other), and bulk-inserts the
diff into this table.  The default is ``False`` because the
set-diff has a small per-row pandas cost; production callers flip it
on explicitly.

Storage / scaling notes mirror :class:`LineageRowEdge` — same
metadata-DB-vs-Delta-table tradeoff, same no-UNIQUE choice (re-runs
that drop the same rows again is informative).

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-26 17:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lineage_row_rejects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("op_id", sa.Integer(), nullable=False),
        sa.Column("source_table", sa.String(length=255), nullable=False),
        sa.Column("source_row_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_lineage_row_rejects_run",
        ),
        sa.ForeignKeyConstraint(
            ["op_id"],
            ["agent_run_operations.id"],
            name="fk_lineage_row_rejects_op",
        ),
        sa.CheckConstraint(
            "reason IN ('on_key_null','schema_mismatch','duplicate_in_source',"
            "'merge_predicate_excluded','other')",
            name="ck_lineage_row_rejects_reason",
        ),
    )
    with op.batch_alter_table("lineage_row_rejects", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_row_rejects_run",
            ["run_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_row_rejects_op",
            ["op_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_row_rejects_source",
            ["source_table", "source_row_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("lineage_row_rejects", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_row_rejects_source")
        batch_op.drop_index("ix_lineage_row_rejects_op")
        batch_op.drop_index("ix_lineage_row_rejects_run")
    op.drop_table("lineage_row_rejects")
