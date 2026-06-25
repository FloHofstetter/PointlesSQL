"""agent_run_operations: extend op_name CHECK with Phase-63 SQL-editor ops

Phase 63 turns the SQL editor from a SELECT-only frontend into a
dispatcher over typed primitives.  The new ops emitted by the
dispatcher branches need to land in ``agent_run_operations``, so
the existing CHECK constraint must be widened.  Six new op names
in one migration to keep the alembic graph compact:

* ``update`` / ``delete`` — new ``pql.update`` / ``pql.delete``
  primitives wrapping ``DeltaTable.update`` / ``.delete``.
* ``drop_table`` — editor ``DROP TABLE`` routed through
  ``pql.drop_table`` instead of a soyuz HTTP call alone.
* ``create_schema`` / ``drop_schema`` — editor schema DDL
  routed through the soyuz facade.
* ``alter_table`` — editor ``ALTER TABLE`` routed through
  the soyuz ``update_table`` facade.

The ``VALID_OP_NAMES`` Python frozen set in
``pointlessql.services.agent_runs.operations._common`` is derived
from the :class:`OpName` enum, so updating the enum and this
CHECK in lockstep keeps both gates aligned.

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-10 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
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
)
_OP_NAMES_OLD = tuple(
    n
    for n in _OP_NAMES_NEW
    if n
    not in {
        "update",
        "delete",
        "drop_table",
        "create_schema",
        "drop_schema",
        "alter_table",
    }
)


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Allow Phase-63 SQL-editor op_names."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Restore the pre-Phase-63 op_name CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )
