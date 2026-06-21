"""agent_runs add harness column

Adds the agent framework / meta-harness name to each supervised run so
the agent-gateway governance console can roll spend and run telemetry
up by harness.  Nullable + free-form: legacy rows and runtimes that do
not report a harness stay queryable, and a new harness needs no further
migration.  The accompanying index keeps the per-harness rollup cheap.

Revision ID: 7931778a18d8
Revises: e9895b37e384
Create Date: 2026-06-20 20:28:08.206439
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7931778a18d8"
down_revision: str | None = "e9895b37e384"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``harness`` column and its rollup index."""
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("harness", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_agent_runs_harness", ["harness"], unique=False)


def downgrade() -> None:
    """Drop the ``harness`` column and its index."""
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_runs_harness")
        batch_op.drop_column("harness")
