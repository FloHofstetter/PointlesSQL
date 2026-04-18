"""Create rate_limit_events table for Sprint 43 auth-surface rate limiting.

Revision ID: 010
Revises: 009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``rate_limit_events`` plus the ``(bucket, created_at)`` index.

    The middleware counts rows per bucket within a time window and
    deletes rows older than the window on every check. Both queries
    are satisfied by the composite index, keeping the limiter's
    amortised cost at one index seek per auth request.
    """
    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bucket", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_events_bucket_created",
        "rate_limit_events",
        ["bucket", "created_at"],
    )


def downgrade() -> None:
    """Drop the ``rate_limit_events`` table and its index."""
    op.drop_index("ix_rate_limit_events_bucket_created", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
