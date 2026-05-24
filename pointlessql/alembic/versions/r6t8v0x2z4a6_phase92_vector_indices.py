"""Phase 92 — vector_indices table + op_name CHECK extension

Sets up the metadata surface for the vector-search compute primitive
introduced in Phase 92:

* New table ``vector_indices`` keyed by
  ``(workspace_id, catalog, schema, table, column)`` — one row per
  duckdb-vss HNSW index that lives next to a Delta table on disk.
* Extends the ``agent_run_operations.op_name`` CHECK constraint to
  accept the new ``vector_index`` and ``vector_search`` op names
  emitted by the primitive's ``operation_context`` wraps.

The ``OpName`` Python StrEnum in
``pointlessql.types._enums`` is updated in the same commit so the
:data:`VALID_OP_NAMES` frozen set (derived from the enum) stays in
lockstep with the DB-side CHECK.

Revision ID: r6t8v0x2z4a6
Revises: q5s7u9w1y3a5
Create Date: 2026-05-19 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r6t8v0x2z4a6"
down_revision: str | None = "q5s7u9w1y3a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OP_NAMES_NEW = (
    "autoload",
    "merge",
    "write_table",
    "sql",
    "aggregate",
    "rollback",
    "train_model",
    "branch_create",
    "branch_promote",
    "branch_discard",
    "dbt_model",
    "dbt_test",
    "sql_explain",
    "update",
    "delete",
    "drop_table",
    "create_schema",
    "drop_schema",
    "alter_table",
    "vector_index",
    "vector_search",
)
_OP_NAMES_OLD = tuple(
    n
    for n in _OP_NAMES_NEW
    if n
    not in {
        "vector_index",
        "vector_search",
    }
)


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Create ``vector_indices`` and extend the op_name CHECK."""
    op.create_table(
        "vector_indices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("catalog", sa.String(length=255), nullable=False),
        sa.Column("schema", sa.String(length=255), nullable=False),
        sa.Column("table", sa.String(length=255), nullable=False),
        sa.Column("column", sa.String(length=255), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("embedder", sa.String(length=64), nullable=False),
        sa.Column(
            "metric",
            sa.String(length=16),
            nullable=False,
            server_default="cosine",
        ),
        sa.Column("hnsw_m", sa.Integer(), nullable=False, server_default="16"),
        sa.Column(
            "hnsw_ef_construction",
            sa.Integer(),
            nullable=False,
            server_default="128",
        ),
        sa.Column("index_path", sa.Text(), nullable=False),
        sa.Column("delta_version_indexed", sa.BigInteger(), nullable=True),
        sa.Column("last_built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_built_rows", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "catalog",
            "schema",
            "table",
            "column",
            name="uq_vector_indices_target",
        ),
    )
    op.create_index(
        "ix_vector_indices_table",
        "vector_indices",
        ["workspace_id", "catalog", "schema", "table"],
    )

    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Drop ``vector_indices`` and restore the pre-Phase-92 op_name CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )

    op.drop_index("ix_vector_indices_table", table_name="vector_indices")
    op.drop_table("vector_indices")
