"""phase 145: auto-discovery entity-link candidates

Adds the persistence the candidate-generator + steward review queue
need:

* ``entity_link_candidates`` — one row per discovered candidate pair.
  CHECK-bounded ``kind`` (``same_as`` / ``derives_from``) and
  ``decision`` (``accepted`` / ``rejected`` / ``deferred`` / NULL
  for pending).  Confidence score is Numeric(3,2) so 0.00..0.99 fit
  exactly; evidence_json carries the scorer breakdown.
* UNIQUE(source_entity_id, target_entity_id, kind) prevents
  duplicate candidates on every scheduler tick.

Revision ID: h5t7v9x1z3b5
Revises: f3r5t7v9x1z3
Create Date: 2026-05-30 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h5t7v9x1z3b5"
down_revision: str | None = "f3r5t7v9x1z3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the entity-link candidates table."""
    op.create_table(
        "entity_link_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_entity_id",
            sa.Integer(),
            sa.ForeignKey("data_product_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Integer(),
            sa.ForeignKey("data_product_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "kind IN ('same_as','derives_from')",
            name="ck_entity_link_candidates_kind",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('accepted','rejected','deferred')",
            name="ck_entity_link_candidates_decision",
        ),
        sa.UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "kind",
            name="uq_entity_link_candidates_triple",
        ),
    )
    op.create_index(
        "ix_entity_link_candidates_pending",
        "entity_link_candidates",
        ["decision", "confidence_score"],
    )


def downgrade() -> None:
    """Drop the entity-link candidates table."""
    op.drop_index(
        "ix_entity_link_candidates_pending",
        table_name="entity_link_candidates",
    )
    op.drop_table("entity_link_candidates")
