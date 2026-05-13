"""user profiles + user-to-user follows + badges (Phase 76.2)

Adds the three tables underpinning ``/users/{id}`` profile pages
+ user-to-user follows + sticky reputation badges:

* ``user_profiles`` (1:1 with ``users``) — bio markdown, avatar
  URL, location, JSON links.  ``user_id`` is both PK and FK so a
  profile cannot outlive the user row.
* ``user_follows`` — composite-PK self-loop on ``users``.  A
  ``CHECK`` constraint forbids self-follow.
* ``user_badges`` — typed positive-only awards.  ``UNIQUE(user_id,
  badge_key)`` so the ``_user_badges_loop`` is idempotent.

Revision ID: q8s0u2w4y6a8
Revises: p7r9t1v3x5z7
Create Date: 2026-05-13 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "q8s0u2w4y6a8"
down_revision: str | None = "p7r9t1v3x5z7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_profiles + user_follows + user_badges."""
    op.create_table(
        "user_profiles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("bio_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column(
            "links_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "user_follows",
        sa.Column(
            "follower_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "followed_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "follower_user_id",
            "followed_user_id",
            name="pk_user_follows",
        ),
        sa.CheckConstraint(
            "follower_user_id <> followed_user_id",
            name="ck_user_follows_no_self",
        ),
    )
    op.create_index(
        "ix_user_follows_followed",
        "user_follows",
        ["followed_user_id", "created_at"],
    )

    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("badge_key", sa.String(length=40), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("awarded_for_count", sa.Integer(), nullable=True),
        sa.UniqueConstraint(
            "user_id", "badge_key", name="uq_user_badge"
        ),
    )
    op.create_index("ix_user_badges_user", "user_badges", ["user_id"])


def downgrade() -> None:
    """Drop the three tables."""
    op.drop_index("ix_user_badges_user", table_name="user_badges")
    op.drop_table("user_badges")
    op.drop_index("ix_user_follows_followed", table_name="user_follows")
    op.drop_table("user_follows")
    op.drop_table("user_profiles")
