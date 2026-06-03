"""notification attention tier

Adds a nullable ``attention`` column to ``user_notifications``.  The
fan-out side stamps ``'for_you'`` when a recipient was explicitly
addressed (an @mention or a directed terminal fact) and ``'ambient'``
when the row only arrived because the recipient follows the entity.
The feed reads this to split a finite "needs you" inbox from the
infinite ambient stream without re-deriving intent from the event
type.  Nullable so existing rows keep working; the feed falls back to
the event type for the legacy ``NULL`` case.

Revision ID: r6f8h0j2l4n6
Revises: q5e7g9i1k3m5
Create Date: 2026-06-02 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r6f8h0j2l4n6"
down_revision: str | None = "q5e7g9i1k3m5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``attention`` column to user_notifications."""
    op.add_column(
        "user_notifications",
        sa.Column("attention", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``attention`` column."""
    op.drop_column("user_notifications", "attention")
