"""agent_run_operations: extend op_name CHECK with branch_* op names

The branching primitives (``pql.branch`` / ``pql.branch_promote`` /
``pql.branch_discard``) call ``operation_context`` with the op_names
``branch_create`` / ``branch_promote`` / ``branch_discard`` (see
``pointlessql/pql/_branch.py``).  Pre-existing tests never passed an
``agent_run_id`` to those primitives, so the audit-write path was
silent and the CHECK constraint never saw the new names.  When an
agent (or our full-stack-demo script) actually runs branching with a
forwarded run id, the insert fails with ``CHECK constraint failed:
ck_agent_run_operations_op_name``.

This migration extends the CHECK to cover the three branch op_names
plus the seven already allowed.  The ``VALID_OP_NAMES`` Python frozen
set in ``pointlessql/services/agent_runs/operations.py`` is updated in
the same commit so both gates agree.

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-30 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
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
)
_OP_NAMES_OLD = _OP_NAMES_NEW[:-3]


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Allow branch_create / branch_promote / branch_discard op_names."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Restore the earlier.x op_name CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )
