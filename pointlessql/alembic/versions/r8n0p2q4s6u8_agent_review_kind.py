"""agent_reviews kind discriminator (Phase 21.6)

Adds a non-null ``kind`` column to ``agent_reviews`` so model-promotion
reviews coexist with the Phase-19 daily audit-review rows. Existing
rows get backfilled to ``"audit_review"`` via a server-side default.

Revision ID: r8n0p2q4s6u8
Revises: q7m9o1p3r5t7
Create Date: 2026-04-30 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r8n0p2q4s6u8"
down_revision: str | None = "q7m9o1p3r5t7"
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
