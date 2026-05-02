"""op_name CHECK constraint extended by 'rollback'

 opens  (First-Class Rollback) by adding the
``pql.rollback`` primitive, which emits ``agent_run_operations`` rows
with ``op_name = 'rollback'``.  The CHECK constraint installed by
``e5f6a7b8c9d0`` covers
``autoload``/``merge``/``write_table``/``sql``/``aggregate`` but
rejects the new value with ``CHECK constraint failed``.

This migration drops the old constraint and re-creates it with
``rollback`` included.  The model in
``pointlessql/models/agent_run_audit.py`` is the source of truth;
this migration brings the deployed DB into agreement.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-04-27 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "i9d0e1f2a3b4"
down_revision: str | None = "h8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_run_operations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            "op_name IN ('autoload','merge','write_table','sql','aggregate','rollback')",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_run_operations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            "op_name IN ('autoload','merge','write_table','sql','aggregate')",
        )
