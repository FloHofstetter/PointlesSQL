"""agent_reviews kind discriminator

Adds a non-null ``kind`` column to ``agent_reviews`` so model-promotion
reviews coexist with the  daily audit-review rows. Existing
rows get backfilled to ``"audit_review"`` via a server-side default.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-30 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the ``kind`` discriminator column + index."""
    op.add_column(
        "agent_reviews",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="audit_review",
        ),
    )
    op.create_index(
        "ix_agent_reviews_kind",
        "agent_reviews",
        ["kind"],
    )


def downgrade() -> None:
    """Drop the ``kind`` index + column."""
    op.drop_index("ix_agent_reviews_kind", "agent_reviews")
    op.drop_column("agent_reviews", "kind")
