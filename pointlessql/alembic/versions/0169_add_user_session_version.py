"""add user session_version for jwt revocation

Adds a server-side session-revocation counter to ``users``.  Every issued
JWT carries the value at mint time as its ``sv`` claim; bumping the column
(on logout or an admin force-revoke) invalidates every token minted before
the bump, since the stale ``sv`` no longer matches the row.

Revision ID: 0169
Revises: 0168
Create Date: 2026-06-23 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0169"
down_revision: str | None = "0168"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``session_version`` column (NOT NULL, default 0)."""
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    """Drop the ``session_version`` column."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("session_version")
