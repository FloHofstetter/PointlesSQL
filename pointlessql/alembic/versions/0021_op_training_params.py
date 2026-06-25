"""agent_run_operations training_params_json

Adds a nullable JSON column for MLflow autolog params + metrics
captured by ``pql.training_context()``. The column is a Text blob
holding a sort-keyed JSON object with ``params`` and ``metrics``
sub-keys; the Run-detail page renders it as an accordion card next
to the operation row.

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-30 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
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
)
_OP_NAMES_OLD = _OP_NAMES_NEW[:-1]


def _ck_clause(names: tuple[str, ...]) -> str:
    quoted = ",".join(f"'{n}'" for n in names)
    return f"op_name IN ({quoted})"


def upgrade() -> None:
    """Add ``training_params_json`` and extend op_name CHECK with ``train_model``."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.add_column(sa.Column("training_params_json", sa.Text(), nullable=True))
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_NEW),
        )


def downgrade() -> None:
    """Drop the ``training_params_json`` column and restore the old CHECK."""
    with op.batch_alter_table("agent_run_operations", recreate="auto") as batch:
        batch.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch.create_check_constraint(
            "ck_agent_run_operations_op_name",
            _ck_clause(_OP_NAMES_OLD),
        )
        batch.drop_column("training_params_json")
