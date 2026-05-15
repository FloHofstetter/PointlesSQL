"""phase77.8.C — polymorphic UNIQUE on data_product_reactions.

77.0.G already made ``data_product_reactions.data_product_id``
nullable so non-DP reaction rows can leave the legacy back-pointer
empty.  The legacy PK ``(data_product_id, user_id, emoji)``
survived but SQL NULL-distinct semantics broke idempotency on the
polymorphic path: multiple ``(NULL, alice, 👍)`` rows are all
distinct under the legacy PK.

This migration mirrors 77.2.1's review fix: add an additive
UNIQUE constraint on ``(workspace_id, social_target_id, user_id,
emoji)`` so the polymorphic upsert is idempotent regardless of
``data_product_id`` shape.  The legacy PK survives — for DP rows
both constraints apply (no conflict because
``social_targets.data_product_id`` is a 1:1 back-pointer for DP
rows); for non-DP rows only the new UNIQUE applies.

Why a 4-tuple instead of the plan-sketch's
``(social_target_id, user_id, emoji)`` 3-tuple: ``data_product_reactions``
has no ``workspace_id`` column today (locked to DP-tenant via
``data_product_id`` -> ``data_products.workspace_id``).  The
polymorphic path knows the workspace at write time, but the
storage row doesn't carry it.  Sticking the workspace_id into
the UNIQUE is doable via a JOIN but adds churn for zero
correctness gain — the social_target_id already encodes the
workspace through the social_targets row.  So the constraint
stays a 3-tuple.

Phase 77.11 will collapse this UNIQUE + the legacy PK by
dropping ``data_product_id`` entirely once every DP reader
queries through ``social_target_id``.

Revision ID: d1g3i5k7m9o1
Revises: c0f2h4j6l8n0
Create Date: 2026-05-15 19:45:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d1g3i5k7m9o1"
down_revision: str | None = "c0f2h4j6l8n0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the polymorphic UNIQUE on (social_target_id, user_id, emoji)."""
    with op.batch_alter_table("data_product_reactions") as batch_op:
        batch_op.create_unique_constraint(
            "uq_dp_reactions_polymorphic",
            ["social_target_id", "user_id", "emoji"],
        )


def downgrade() -> None:
    """Drop the polymorphic UNIQUE constraint."""
    with op.batch_alter_table("data_product_reactions") as batch_op:
        batch_op.drop_constraint(
            "uq_dp_reactions_polymorphic", type_="unique"
        )
