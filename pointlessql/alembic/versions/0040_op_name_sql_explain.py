"""agent_run_operations: extend op_name CHECK with sql_explain

Phase 39 Sprint 39.1 introduces a per-run audit row whenever an
agent submits SQL through ``GET /api/sql/explain`` while carrying an
``X-Agent-Run-Id`` header — the LLM looking at a query's plan +
cost-gate verdict before execution is itself an audit-relevant
operation.  Without this CHECK extension the insert would refuse.

The Python ``VALID_OP_NAMES`` frozen set in
``pointlessql/services/agent_runs/operations.py`` is updated in the
same commit so both gates agree.

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-06 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
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
)
_OP_NAMES_OLD = _OP_NAMES_NEW[:-1]


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Allow sql_explain op_name."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Restore the pre-Phase-39 op_name CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )
