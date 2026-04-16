"""Add jobs.on_failure_url for Sprint 21 failure webhooks.

Revision ID: 007
Revises: 006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``on_failure_url`` column on ``jobs``.

    Opt-in — existing rows keep ``NULL`` and the scheduler's webhook
    path is a no-op for them. String length is generous enough to hold
    any modern HTTPS endpoint (GitHub/PagerDuty alike stay under 400
    characters) without bloating the row.
    """
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(
            sa.Column(
                "on_failure_url",
                sa.String(1000),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Drop the ``on_failure_url`` column."""
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("on_failure_url")
