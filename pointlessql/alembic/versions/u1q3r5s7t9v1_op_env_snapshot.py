"""agent_run_operations env_snapshot

Adds a nullable Text column for an advisory hardware/library
fingerprint snapshot.  The snapshot is captured at module-import
time once per PointlesSQL process (cheap on the hot path) and
written verbatim onto every agent-run operation that succeeds,
giving the Audit-Cockpit / Run-detail UI a "what env produced
this row?" answer without needing the operator to remember to
``pip freeze`` first.

Per ROADMAP.md (lines 2325-2332): "auditability of intent, not
bit-replay" — the snapshot is descriptive, never normative.

Revision ID: u1q3r5s7t9v1
Revises: t0p2q4r6s8u0
Create Date: 2026-04-30 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "u1q3r5s7t9v1"
down_revision: str | None = "t0p2q4r6s8u0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``env_snapshot`` Text column."""
    op.add_column(
        "agent_run_operations",
        sa.Column("env_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``env_snapshot`` column."""
    op.drop_column("agent_run_operations", "env_snapshot")
