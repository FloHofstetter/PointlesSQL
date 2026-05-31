"""phase 155: dp canvas — is_production pin flag + canvas_pin/unpin ops

Adds a per-version production-pin flag on
``data_product_canvas_graph`` so the visual editor can mark exactly one
saved canvas version per data product as "the live production
revision" (separate from "the latest draft").  Lookups for
``is_production = TRUE`` are common — every editor open and every
materialise pre-check asks "is the current draft replacing the pinned
production version?" — so the column gets a partial unique index that
both indexes the lookup *and* enforces "at most one production version
per product" at the database level.

Pairs with two new ``OpName`` values (``canvas_pin`` /
``canvas_unpin``) so the pin-toggle service can stamp one
``agent_run_operations`` row per change without tripping the
``op_name`` CHECK constraint.

Revision ID: m1a3c5e7g9i1
Revises: l9x1z3b5d7f9
Create Date: 2026-05-31 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m1a3c5e7g9i1"
down_revision: str | None = "l9x1z3b5d7f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OP_NAMES_OLD = (
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
    "pin_fact",
    "canvas_materialize",
)
_OP_NAMES_NEW = (*_OP_NAMES_OLD, "canvas_pin", "canvas_unpin")


def _op_name_ck(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Add ``is_production`` column + partial unique index, widen op_name CHECK."""
    with op.batch_alter_table("data_product_canvas_graph") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_production",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect in ("postgresql", "sqlite"):
        op.execute(
            "CREATE UNIQUE INDEX idx_unique_production_per_dp "
            "ON data_product_canvas_graph (data_product_id) "
            "WHERE is_production = 1"
            if dialect == "sqlite"
            else "CREATE UNIQUE INDEX idx_unique_production_per_dp "
            "ON data_product_canvas_graph (data_product_id) "
            "WHERE is_production = TRUE"
        )
    else:
        op.create_index(
            "idx_unique_production_per_dp",
            "data_product_canvas_graph",
            ["data_product_id", "is_production"],
            unique=True,
        )

    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Revert op_name CHECK; drop unique index + is_production column."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_OLD),
        )

    op.drop_index(
        "idx_unique_production_per_dp",
        table_name="data_product_canvas_graph",
    )
    with op.batch_alter_table("data_product_canvas_graph") as batch_op:
        batch_op.drop_column("is_production")
