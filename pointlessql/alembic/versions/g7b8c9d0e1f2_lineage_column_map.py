"""lineage_column_map table for column-level lineage

Sibling to ``lineage_row_edges`` covering the orthogonal column
dimension.  Every PQL primitive populates one row per
``(source_column, target_column)`` mapping per op, with a
``transform_kind`` that classifies how the source feeds the target:
``identity`` / ``rename`` / ``derived`` / ``aggregate`` /
``unknown_origin`` for the declarative path, plus
``sql_select`` / ``sql_function`` / ``sql_unknown`` for the
sqlglot-AST path on ``pql.sql``.

Volume contract: bounded by **schema breadth**, not row count.  The
canonical Hermes-Medallion run produces ~26 column edges total
against the 102 row edges + 2 rejects from .  The
``record_column_edges`` service helper enforces a 1000-edge cap per
op as a safety net for pathological ``pql.sql`` queries.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-26 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lineage_column_map",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("op_id", sa.Integer(), nullable=False),
        sa.Column("source_table", sa.String(length=255), nullable=True),
        sa.Column("source_column", sa.String(length=255), nullable=True),
        sa.Column("target_table", sa.String(length=255), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("transform_kind", sa.String(length=32), nullable=False),
        sa.Column("transform_detail", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_lineage_column_map_run",
        ),
        sa.ForeignKeyConstraint(
            ["op_id"],
            ["agent_run_operations.id"],
            name="fk_lineage_column_map_op",
        ),
        sa.CheckConstraint(
            "transform_kind IN ('identity','rename','derived','aggregate',"
            "'unknown_origin','sql_select','sql_function','sql_unknown')",
            name="ck_lineage_column_map_transform_kind",
        ),
    )
    with op.batch_alter_table("lineage_column_map", schema=None) as batch_op:
        batch_op.create_index(
            "ix_lineage_column_map_run",
            ["run_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_column_map_op",
            ["op_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_column_map_target",
            ["target_table", "target_column"],
            unique=False,
        )
        batch_op.create_index(
            "ix_lineage_column_map_source",
            ["source_table", "source_column"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("lineage_column_map", schema=None) as batch_op:
        batch_op.drop_index("ix_lineage_column_map_source")
        batch_op.drop_index("ix_lineage_column_map_target")
        batch_op.drop_index("ix_lineage_column_map_op")
        batch_op.drop_index("ix_lineage_column_map_run")
    op.drop_table("lineage_column_map")
