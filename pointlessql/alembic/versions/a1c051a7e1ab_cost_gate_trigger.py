"""cost_gate_trigger column on agent_runs

Adds a nullable JSON-as-Text column that captures the EXPLAIN
snapshot the cost gate fired on, so a reviewer of a denied run can
see WHY without re-running the query (Sprint 14.1).

Revision ID: a1c051a7e1ab
Revises: b55f1020b8a4
Create Date: 2026-04-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c051a7e1ab"
down_revision: str | None = "b55f1020b8a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cost_gate_trigger", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_column("cost_gate_trigger")
