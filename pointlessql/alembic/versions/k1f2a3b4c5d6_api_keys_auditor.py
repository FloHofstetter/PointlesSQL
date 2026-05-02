"""api_keys.auditor scope column

 adds an ``auditor`` Bearer-token scope so the daily
Audit-Reviewer-Agent (and the compliance + incident demos) can read
the ``/api/audit/*`` aggregates and the per-run audit-axis routes
without inheriting admin's PII-reveal capability or supervisor's
approve/deny.  Additive ``BOOLEAN NOT NULL DEFAULT 0`` column on
``api_keys`` — the previous-supervisor / non-supervisor split is
left untouched, so this is a zero-migration-data-risk addition.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-04-28 21:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "k1f2a3b4c5d6"
down_revision: str | None = "j0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "auditor",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_column("auditor")
