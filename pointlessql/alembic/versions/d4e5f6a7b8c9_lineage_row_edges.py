"""lineage_row_edges table for per-row provenance (Sprint 15.3)

Adds the persistence layer for the per-row lineage map produced by
``pql.merge`` (and, when the caller declares ``source_table_fqn``,
``pql.write_table``).  Operation-level lineage already lives in
``agent_run_operations``; this table extends the picture down to
"silver row R came from bronze row S".  Sprint 15.4 walks the graph
backwards for the row-trace UI.

Bronze rows carry their identity in the ``_lineage_row_id`` audit
column (Sprint 15.2 — ``SHA-256("<file_sha>:<offset>")``); merge
synthesises target IDs as ``SHA-256("<source_id>:<target_table>")``
so re-runs reuse target IDs deterministically while still producing
fresh ``op_id``-tagged edges in this table.

Revision ID: d4e5f6a7b8c9
Revises: c3d4f5a6b7e8
Create Date: 2026-04-26 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4f5a6b7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lineage_row_edges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("op_id", sa.Integer(), nullable=False),
        sa.Column("source_table", sa.String(length=255), nullable=False),
        sa.Column("source_row_id", sa.String(length=64), nullable=False),
        sa.Column("target_table", sa.String(length=255), nullable=False),
        sa.Column("target_row_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_lineage_row_edges_run",
        ),
        sa.ForeignKeyConstraint(
            ["op_id"],
            ["agent_run_operations.id"],
            name="fk_lineage_row_edges_op",
        ),
    )
    with op.batch_alter_table("lineage_row_edges", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_row_edges_target",
            ["target_table", "target_row_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_row_edges_source",
            ["source_table", "source_row_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_row_edges_run",
            ["run_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_row_edges_op",
            ["op_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("lineage_row_edges", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_row_edges_op")
        batch_op.drop_index("ix_lineage_row_edges_run")
        batch_op.drop_index("ix_lineage_row_edges_source")
        batch_op.drop_index("ix_lineage_row_edges_target")
    op.drop_table("lineage_row_edges")
