"""topics + DP/topic many-to-many + user-topic follows (Phase 76.3)

Three tables:

* ``topics`` — workspace-scoped taxonomy.  Unique
  ``(workspace_id, slug)``.
* ``data_product_topics`` — m:n join, composite PK
  ``(data_product_id, topic_id)``.
* ``user_topic_follows`` — composite PK ``(user_id, topic_id)``.

The Phase-76.3 surface ships these as discovery-only — comments
stay DP-scoped; topics provide cross-DP grouping + the
``pointlessql.topic.dp_added`` fan-out notification.

Revision ID: r9t1v3x5z7b9
Revises: q8s0u2w4y6a8
Create Date: 2026-05-13 22:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "r9t1v3x5z7b9"
down_revision: str | None = "q8s0u2w4y6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create topics + data_product_topics + user_topic_follows."""
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column(
            "description_md", sa.Text(), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id", "slug", name="uq_topics_slug"
        ),
    )

    op.create_table(
        "data_product_topics",
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "added_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "data_product_id", "topic_id", name="pk_data_product_topics"
        ),
    )
    op.create_index(
        "ix_data_product_topics_topic",
        "data_product_topics",
        ["topic_id"],
    )

    op.create_table(
        "user_topic_follows",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.Integer(),
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "user_id", "topic_id", name="pk_user_topic_follows"
        ),
    )
    op.create_index(
        "ix_user_topic_follows_topic",
        "user_topic_follows",
        ["topic_id"],
    )


def downgrade() -> None:
    """Drop the three tables in dependency order."""
    op.drop_index(
        "ix_user_topic_follows_topic", table_name="user_topic_follows"
    )
    op.drop_table("user_topic_follows")
    op.drop_index(
        "ix_data_product_topics_topic", table_name="data_product_topics"
    )
    op.drop_table("data_product_topics")
    op.drop_table("topics")
