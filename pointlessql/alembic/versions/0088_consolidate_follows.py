"""consolidate ``data_product_follows`` into ``social_follows``.

Phase 77.0.G added the polymorphic ``social_target_id`` back-
pointer to ``data_product_follows`` and 77.8 introduced
``social_follows`` as a kind-agnostic sibling table.  Both tables
were kept in sync during 77.8 dual-write so the legacy follower
queries never broke.

This migration retires the legacy table:

1. Copy every ``data_product_follows`` row into ``social_follows``
   (deduped on the new ``(workspace_id, social_target_id, user_id)``
   PK).
2. Drop ``data_product_follows``.

Pre-flight assert: no ``data_product_follows`` row may carry a
NULL ``social_target_id`` — the 77.0.B backfill is supposed to
have stamped one on every legacy row.  If the assertion fires,
operators re-run that backfill before retrying the migration.

Downgrade recreates ``data_product_follows`` and replays the
polymorphic rows back through the ``social_targets`` →
``data_products`` back-pointer (only ``kind='dp'`` rows survive
the round-trip; non-DP follows live exclusively in
``social_follows`` and would not exist in the legacy table).

Revision ID: 0088
Revises: 0087
Create Date: 2026-05-16 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0088"
down_revision: str | None = "0087"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate DP follow rows into social_follows + drop the legacy table."""
    bind = op.get_bind()

    null_count = bind.execute(
        text("SELECT COUNT(*) FROM data_product_follows WHERE social_target_id IS NULL")
    ).scalar()
    if null_count and int(null_count) > 0:
        raise RuntimeError(
            f"data_product_follows has {null_count} rows with NULL "
            "social_target_id; re-run the Phase-77.0.B backfill "
            "before applying Phase 78 polish."
        )

    bind.execute(
        text(
            "INSERT INTO social_follows ("
            "    workspace_id, social_target_id, user_id, created_at"
            ") SELECT df.workspace_id, df.social_target_id, df.user_id, "
            "         df.created_at "
            "  FROM data_product_follows df "
            "  WHERE NOT EXISTS ("
            "      SELECT 1 FROM social_follows sf "
            "      WHERE sf.workspace_id = df.workspace_id "
            "        AND sf.social_target_id = df.social_target_id "
            "        AND sf.user_id = df.user_id"
            "  )"
        )
    )

    op.drop_index("ix_dp_follows_user", table_name="data_product_follows")
    op.drop_index(
        "ix_data_product_follows_social_target",
        table_name="data_product_follows",
    )
    op.drop_table("data_product_follows")


def downgrade() -> None:
    """Recreate ``data_product_follows`` + replay DP-kind rows."""
    op.create_table(
        "data_product_follows",
        sa.Column(
            "workspace_id",
            sa.Integer(),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "data_product_id",
            sa.Integer(),
            sa.ForeignKey("data_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
            "workspace_id",
            "data_product_id",
            "user_id",
            name="pk_data_product_follows",
        ),
    )
    op.create_index(
        "ix_dp_follows_user",
        "data_product_follows",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_data_product_follows_social_target",
        "data_product_follows",
        ["social_target_id"],
    )
    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO data_product_follows ("
            "    workspace_id, data_product_id, user_id, created_at, social_target_id"
            ") SELECT sf.workspace_id, st.data_product_id, sf.user_id, "
            "         sf.created_at, sf.social_target_id "
            "  FROM social_follows sf "
            "  JOIN social_targets st ON st.id = sf.social_target_id "
            "  WHERE st.entity_kind = 'dp' AND st.data_product_id IS NOT NULL"
        )
    )
