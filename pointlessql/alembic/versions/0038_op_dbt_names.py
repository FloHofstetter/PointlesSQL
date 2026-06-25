"""agent_run_operations: extend op_name CHECK with dbt_* op names

Phase 36 introduces the dbt-bridge ops ``dbt_model`` and ``dbt_test``
(see ``pointlessql/services/dbt_bridge.py``).  They are inserted via
the same ``record_operation`` path as every other PQL op, so the
existing CHECK constraint refuses them until extended here.

The ``VALID_OP_NAMES`` Python frozen set in
``pointlessql/services/agent_runs/operations.py`` is updated in the
same commit (Sprint 36.2) so both gates agree.

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-06 12:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
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
)
_OP_NAMES_OLD = _OP_NAMES_NEW[:-2]


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Allow dbt_model / dbt_test op_names."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Restore the earlier branch-only op_name CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )
