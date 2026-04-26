"""op_name CHECK constraint extended by 'aggregate' (Sprint 15.5.1)

Sprint 15.5.1 introduces the ``pql.aggregate`` primitive, which emits
``agent_run_operations`` rows with ``op_name = 'aggregate'``.  The
existing CHECK constraint installed by the squashed initial schema
(``b55f1020b8a4``) only permits ``autoload`` / ``merge`` /
``write_table`` / ``sql``, so unmigrated databases reject the new
op-name with ``CHECK constraint failed``.

This migration drops the old constraint and re-creates it with the
aggregate value included.  The model in
``pointlessql/models/agent_run_audit.py`` is the source of truth;
this migration brings the deployed DB into agreement.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-26 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_run_operations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            "op_name IN ('autoload','merge','write_table','sql','aggregate')",
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_run_operations", schema=None) as batch_op:
        batch_op.drop_constraint("ck_agent_run_operations_op_name", type_="check")
        batch_op.create_check_constraint(
            "ck_agent_run_operations_op_name",
            "op_name IN ('autoload','merge','write_table','sql')",
        )
