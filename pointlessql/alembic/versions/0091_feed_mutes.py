"""Phase 81.K.4 — feed_mutes table for thread mute + snooze.

The new ``/feed`` page lets users hide noisy threads.  Two muting
shapes share one table:

* Mute an entity-or-author indefinitely → ``muted_until IS NULL``.
* Snooze for a fixed window → ``muted_until = now() + duration``.

Author-muting reuses the same row shape with ``entity_kind='user'``
and ``entity_ref`` = the muted user-id (stringified) so the feed
filter is one table scan rather than two.  ``(user_id, entity_kind,
entity_ref)`` is unique — re-muting an entity simply updates the
``muted_until`` column on the existing row.

Revision ID: 0091
Revises: 0090
Create Date: 2026-05-16 11:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0091"
down_revision: str | None = "0090"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``feed_mutes`` table + supporting unique index."""
    op.create_table(
        "feed_mutes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_kind", sa.String(length=32), nullable=False),
        sa.Column("entity_ref", sa.String(length=300), nullable=False),
        sa.Column(
            "muted_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_feed_mutes_per_target",
        "feed_mutes",
        ["user_id", "entity_kind", "entity_ref"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the table + index."""
    op.drop_index("uq_feed_mutes_per_target", table_name="feed_mutes")
    op.drop_table("feed_mutes")
