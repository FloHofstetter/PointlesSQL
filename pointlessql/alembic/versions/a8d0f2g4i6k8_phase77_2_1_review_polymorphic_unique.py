"""phase77.2.1 — polymorphic review UNIQUE on social_target_id.

Phase 77.2 shipped registered-model social tabs but left Reviews
off (``model.supports_reviews=False``).  Reason: the legacy
unique constraint on ``data_product_reviews`` was
``(workspace_id, data_product_id, author_user_id)`` and
``data_product_id`` is NULL for non-DP rows (per 77.0.G's
nullable-FK migration).  SQL NULL-distinct semantics meant a
single user could post multiple reviews on the same model — the
upsert path is broken.

This migration adds a kind-agnostic UNIQUE on
``(workspace_id, social_target_id, author_user_id)`` so the
polymorphic review path is idempotent.  The legacy DP-id-based
UNIQUE stays in place — for DP rows both UNIQUEs apply (no
conflict because ``social_targets.data_product_id`` is a 1:1
back-pointer for DP rows).  Eventually 77.11 unification will
drop the legacy UNIQUE entirely, but additive here keeps the
migration trivially reversible.

The new UNIQUE is safe to add on existing data: legacy DP rows
can't have duplicates on ``(ws, dp_id, user)`` and dp_id maps
1:1 to social_target_id for DP rows, so no
``(ws, social_target_id, user)`` duplicates exist either.  No
seed/backfill needed.

Revision ID: a8d0f2g4i6k8
Revises: z7c9e1g3i5k7
Create Date: 2026-05-15 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a8d0f2g4i6k8"
down_revision: str | None = "z7c9e1g3i5k7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the polymorphic UNIQUE on (ws, social_target_id, user)."""
    with op.batch_alter_table("data_product_reviews") as batch_op:
        batch_op.create_unique_constraint(
            "uq_dp_review_polymorphic_one_per_user",
            ["workspace_id", "social_target_id", "author_user_id"],
        )


def downgrade() -> None:
    """Drop the polymorphic UNIQUE constraint."""
    with op.batch_alter_table("data_product_reviews") as batch_op:
        batch_op.drop_constraint("uq_dp_review_polymorphic_one_per_user", type_="unique")
