"""phase77.8.A — social_stars polymorphic bookmark table.

Stars are the lightweight "I bookmarked this" primitive, separate
from Follow (which signals "I want notifications").  After Phase
77.8 they replace the localStorage-only ``pqlStarToggle`` with
real per-user persistence shared across devices.

The table is polymorphic from day 1 — composite PK on
``(workspace_id, user_id, social_target_id)``.  Adding a new
entity kind in a later sub-phase needs no migration work; just
register the kind in :mod:`entity_registry` and the existing
``/api/social/{kind}/{ref}/star`` path covers it.

No backfill: localStorage stars are intentionally NOT migrated.
Users re-star the entities they care about — the alternative
(scraping every browser's localStorage on first login) is both
impossible cross-device and pointless for a Phase-1 product
where stars are aspirational.

Two indexes round out the table:

* ``ix_social_stars_target`` on ``social_target_id`` — supports
  star-count aggregations grouped by entity (`How many users
  starred this table?`).
* ``ix_social_stars_user`` on ``(user_id, social_target_id)`` —
  supports per-user starred-entity listings for the Phase 77.10
  profile "Starred" tab.

The composite PK already covers the ``workspace_id`` prefix so
no extra workspace index is needed.

Revision ID: b9e1g3i5k7m9
Revises: a8d0f2g4i6k8
Create Date: 2026-05-15 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9e1g3i5k7m9"
down_revision: str | None = "a8d0f2g4i6k8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the social_stars table + two helper indexes."""
    op.create_table(
        "social_stars",
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
            "workspace_id",
            "user_id",
            "social_target_id",
            name="pk_social_stars",
        ),
    )
    op.create_index(
        "ix_social_stars_target",
        "social_stars",
        ["social_target_id"],
    )
    op.create_index(
        "ix_social_stars_user",
        "social_stars",
        ["user_id", "social_target_id"],
    )


def downgrade() -> None:
    """Drop the social_stars table + its indexes."""
    op.drop_index("ix_social_stars_user", table_name="social_stars")
    op.drop_index("ix_social_stars_target", table_name="social_stars")
    op.drop_table("social_stars")
