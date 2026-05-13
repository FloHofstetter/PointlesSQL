"""notification_prefs_json on users (Phase 76.4)

Adds a single nullable-OK JSON column carrying per-event-type
inbox / email / webhook toggles.  Missing keys + missing column
both default to all-true so the migration is naturally backwards-
compatible: every existing user keeps receiving every signal.

Revision ID: s0u2w4y6a8c0
Revises: r9t1v3x5z7b9
Create Date: 2026-05-13 23:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s0u2w4y6a8c0"
down_revision: str | None = "r9t1v3x5z7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``notification_prefs_json`` to users."""
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "notification_prefs_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    """Drop the notification_prefs_json column."""
    with op.batch_alter_table("users") as batch:
        batch.drop_column("notification_prefs_json")
