"""phase 147: visual dp editor — canvas graph version ledger + canvas_materialize op

Two changes, paired because both serve the visual-editor executor:

* Introduces ``data_product_canvas_graph`` — an append-only ledger of
  visual block-and-wire graph versions per data product.  One row per
  saved version; ``version`` is monotonic per ``data_product_id``
  (1-based), guarded by a UNIQUE composite.  ``document`` carries the
  JSON-serialised ``CanvasDoc`` envelope (nodes + edges + schema
  version) the visual editor authored.  CASCADE on the product FK so
  graph history disappears with its product; SET NULL on the author FK
  so versions survive account removal.
* Extends ``ck_agent_run_operations_op_name`` with ``'canvas_materialize'``
  so the new executor can stamp one ``agent_run_operations`` row per
  materialise without tripping the CHECK constraint.  All existing
  values stay valid.

The canvas executor inserts a fresh graph row on every successful
materialise; the Phase 148 frontend reads back the latest version on
editor open and the 154.1 versioning UI lists them all.

Revision ID: l9x1z3b5d7f9
Revises: j7v9x1z3b5d7
Create Date: 2026-05-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l9x1z3b5d7f9"
down_revision: str | None = "j7v9x1z3b5d7"
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
)
_OP_NAMES_NEW = (*_OP_NAMES_OLD, "canvas_materialize")


def _op_name_ck(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Create the canvas graph version ledger + widen the op_name CHECK."""
    op.create_table(
        "data_product_canvas_graph",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column(
            "author_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "data_product_id",
            "version",
            name="uq_dp_canvas_graph_dp_version",
        ),
    )
    op.create_index(
        "ix_dp_canvas_graph_dp",
        "data_product_canvas_graph",
        ["data_product_id"],
    )

    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Revert the op_name CHECK + drop the canvas graph ledger."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _op_name_ck(_OP_NAMES_OLD),
        )

    op.drop_index(
        "ix_dp_canvas_graph_dp",
        table_name="data_product_canvas_graph",
    )
    op.drop_table("data_product_canvas_graph")
