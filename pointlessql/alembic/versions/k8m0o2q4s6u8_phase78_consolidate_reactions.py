"""phase78 polish — consolidate reactions + drop legacy review UNIQUE.

Two cleanups bundled because both retire 77.8-era transitional
state on tables that had to grow polymorphic-secondary
constraints to support non-DP kinds:

1. ``data_product_reactions`` had a sibling-table polymorphic
   UNIQUE added in 77.8.C alongside the unnamed legacy PK on
   ``(data_product_id, user_id, emoji)``.  SQLite's unnamed-PK
   reflection prevents :func:`op.drop_constraint`, so we use the
   sibling-table pattern documented in the 77.8.B post-mortem:
   create ``social_reactions`` with the kind-agnostic PK, copy
   rows that carry a ``social_target_id``, then drop the legacy
   table.

2. ``data_product_reviews.uq_dp_review_one_per_user`` (Phase
   71.2) was made redundant in 77.2.1 by the polymorphic
   ``uq_dp_review_one_per_user_polymorphic`` UNIQUE.  Drop the
   legacy constraint — the polymorphic one covers DP rows via
   the 1:1 ``social_targets.data_product_id`` back-pointer.

Downgrade recreates ``data_product_reactions`` with a *named*
legacy PK (avoids the unnamed-implicit-PK issue on re-up) and
re-adds the legacy review UNIQUE.

Revision ID: k8m0o2q4s6u8
Revises: j7l9n1p3r5t7
Create Date: 2026-05-16 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "k8m0o2q4s6u8"
down_revision: str | None = "j7l9n1p3r5t7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Sibling-table reaction swap + drop the legacy review UNIQUE."""
    bind = op.get_bind()

    # 1. Reactions sibling-table swap.
    op.create_table(
        "social_reactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "social_target_id",
            "user_id",
            "emoji",
            name="uq_social_reactions_one_per_user_per_emoji",
        ),
    )
    op.create_index(
        "ix_social_reactions_target",
        "social_reactions",
        ["social_target_id"],
    )

    pre_count = bind.execute(
        text("SELECT COUNT(*) FROM data_product_reactions WHERE social_target_id IS NOT NULL")
    ).scalar()
    bind.execute(
        text(
            "INSERT INTO social_reactions ("
            "    social_target_id, user_id, emoji, created_at"
            ") SELECT social_target_id, user_id, emoji, created_at "
            "  FROM data_product_reactions "
            "  WHERE social_target_id IS NOT NULL"
        )
    )
    post_count = bind.execute(text("SELECT COUNT(*) FROM social_reactions")).scalar()
    if int(post_count or 0) != int(pre_count or 0):
        raise RuntimeError(
            f"social_reactions seed mismatch: copied {post_count} rows but "
            f"data_product_reactions had {pre_count} polymorphic-ready rows"
        )

    op.drop_index(
        "ix_data_product_reactions_social_target",
        table_name="data_product_reactions",
    )
    op.drop_index("ix_dp_reactions_dp", table_name="data_product_reactions")
    op.drop_table("data_product_reactions")

    # 2. Drop the legacy review UNIQUE (the polymorphic one stays).
    with op.batch_alter_table("data_product_reviews") as batch:
        batch.drop_constraint("uq_dp_review_one_per_user", type_="unique")


def downgrade() -> None:
    """Recreate the legacy reactions table + the legacy review UNIQUE."""
    with op.batch_alter_table("data_product_reviews") as batch:
        batch.create_unique_constraint(
            "uq_dp_review_one_per_user",
            ["workspace_id", "data_product_id", "author_user_id"],
        )

    op.create_table(
        "data_product_reactions",
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("emoji", sa.String(10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "social_target_id",
            sa.Integer(),
            sa.ForeignKey("social_targets.id"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "data_product_id",
            "user_id",
            "emoji",
            name="pk_dp_reactions",
        ),
        sa.UniqueConstraint(
            "social_target_id",
            "user_id",
            "emoji",
            name="uq_dp_reactions_polymorphic",
        ),
    )
    op.create_index("ix_dp_reactions_dp", "data_product_reactions", ["data_product_id"])
    op.create_index(
        "ix_data_product_reactions_social_target",
        "data_product_reactions",
        ["social_target_id"],
    )
    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO data_product_reactions ("
            "    data_product_id, user_id, emoji, created_at, social_target_id"
            ") SELECT st.data_product_id, sr.user_id, sr.emoji, sr.created_at, "
            "         sr.social_target_id "
            "  FROM social_reactions sr "
            "  JOIN social_targets st ON st.id = sr.social_target_id "
            "  WHERE st.entity_kind = 'dp' AND st.data_product_id IS NOT NULL"
        )
    )
    op.drop_index("ix_social_reactions_target", table_name="social_reactions")
    op.drop_table("social_reactions")
