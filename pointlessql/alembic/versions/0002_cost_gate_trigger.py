"""cost_gate_trigger column on agent_runs

Adds a nullable JSON-as-Text column that captures the EXPLAIN
snapshot the cost gate fired on, so a reviewer of a denied run can
see WHY without re-running the query.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cost_gate_trigger", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_column("cost_gate_trigger")
