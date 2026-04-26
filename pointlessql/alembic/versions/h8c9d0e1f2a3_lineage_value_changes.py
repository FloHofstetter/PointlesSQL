"""lineage_value_changes table for value-level lineage (Sprint 15.7.1)

Fourth lineage axis after row (Phase 15), reject (15.5), column (15.6).
Records per-cell before/after pairs produced by
``pql.merge(strategy="upsert", track_value_changes=True)``.  Capture
mechanic: every new Delta write enables Change Data Feed
(``delta.enableChangeDataFeed=true``); post-merge ``load_cdf()``
yields preimage / postimage records that the diff helper pairs on
``_lineage_row_id``.

Volume contract: bounded by *matched-and-actually-different* cells.
A re-run with identical input produces zero rows (postimage ==
preimage → skip).  ``MAX_VALUE_CHANGES_PER_OP = 100_000`` cap with
``[lineage_value_partial]`` audit-row marker on hit.  ``old_value`` /
``new_value`` are SQLAlchemy ``Text`` (unbounded) — typical lakehouse
values are tiny strings, but JSON / map columns can be arbitrary
size and we don't want truncation to mask diffs.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-04-26 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h8c9d0e1f2a3"
down_revision: str | None = "g7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lineage_value_changes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("op_id", sa.Integer(), nullable=False),
        sa.Column("target_table", sa.String(length=255), nullable=False),
        sa.Column("target_row_id", sa.String(length=64), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_lineage_value_changes_run",
        ),
        sa.ForeignKeyConstraint(
            ["op_id"],
            ["agent_run_operations.id"],
            name="fk_lineage_value_changes_op",
        ),
    )
    with op.batch_alter_table("lineage_value_changes", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_value_changes_run",
            ["run_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_value_changes_op",
            ["op_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_value_changes_target_row",
            ["target_table", "target_row_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_value_changes_target_col",
            ["target_table", "target_column"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("lineage_value_changes", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_value_changes_target_col")
        batch_op.drop_index("ix_lineage_value_changes_target_row")
        batch_op.drop_index("ix_lineage_value_changes_op")
        batch_op.drop_index("ix_lineage_value_changes_run")
    op.drop_table("lineage_value_changes")
