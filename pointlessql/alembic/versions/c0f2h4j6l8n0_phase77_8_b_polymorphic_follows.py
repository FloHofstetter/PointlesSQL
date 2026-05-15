"""phase77.8.B — social_follows polymorphic follow-table.

Before Phase 77.8 the ``data_product_follows`` PK was the composite
``(workspace_id, data_product_id, user_id)`` — the polymorphic
``social_target_id`` anchor landed in 77.0.B as a non-PK column.
77.0.G's docstring flagged this explicitly:

    Follows carries ``data_product_id`` as part of its composite PK
    ``(workspace_id, data_product_id, user_id)``, so the column
    cannot be NULLed without restructuring the PK.  Non-dp follow
    primitives land in a separate polymorphic ``social_stars`` /
    ``social_follows`` table in 77.8 / later sub-phase.

This migration follows that path: it creates a new
``social_follows`` table for polymorphic follows.  Phase 77.8.D
will flip the 501-gated polymorphic follow handler to write here.
The legacy ``data_product_follows`` table is left untouched —
the DP follow route keeps using it unchanged, and the fanout
service still resolves DP followers via the legacy table.

The unified rename (``social_follows`` + ``data_product_follows``
collapsing into a single polymorphic table) is deferred to Phase
77.11 alongside the renames of ``data_product_readmes`` →
``entity_readmes`` and ``data_product_reactions`` →
``social_reactions``.  Splitting the migration here keeps the
SQLite path simple — no PK restructure needed.

Schema:

* ``social_follows(workspace_id, user_id, social_target_id,
  created_at)`` — composite PK on ``(workspace_id,
  social_target_id, user_id)``.
* ``ix_social_follows_user`` on ``(user_id, created_at)`` —
  inbox / notification path.

No backfill: DP follow rows stay in ``data_product_follows``.
``social_follows`` starts empty.  When 77.11 unifies, the DP
rows are migrated then.

Revision ID: c0f2h4j6l8n0
Revises: b9e1g3i5k7m9
Create Date: 2026-05-15 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c0f2h4j6l8n0"
down_revision: str | None = "b9e1g3i5k7m9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the polymorphic ``social_follows`` table."""
    op.create_table(
        "social_follows",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id", "social_target_id", "user_id",
            name="pk_social_follows",
        ),
    )
    op.create_index(
        "ix_social_follows_user",
        "social_follows",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    """Drop the ``social_follows`` table + its inbox-axis index."""
    op.drop_index("ix_social_follows_user", table_name="social_follows")
    op.drop_table("social_follows")
