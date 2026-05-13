"""phase77 — polymorphic source markers on ``user_notifications``

Adds two nullable columns on ``user_notifications`` so the
post-77.0 ``fanout_event(...)`` dispatcher can stamp the source
entity kind + ref on every row it emits, without breaking the
legacy ``source_data_product_id`` back-compat path that hermes-
plugin-pointlessql H.3 tools depend on.

* ``source_entity_kind VARCHAR(32) NULL`` — discriminator from
  :data:`pointlessql.models.social.ENTITY_KINDS`.  Populated by
  every new dispatch path; ``NULL`` for the legacy
  ``fanout_dataproduct_event`` wrapper that exists for two more
  sub-sprints before deletion in 77.11.
* ``source_entity_ref VARCHAR(500) NULL`` — opaque entity
  reference (FQN for UC, numeric id for PointlesSQL-owned
  entities, UUID for notebooks).

No backfill — historic rows keep their ``source_data_product_id``
and stay ``NULL`` on the new columns.  Feed-row rendering looks
at ``source_entity_kind`` first; falls back to the legacy DP
back-pointer when ``NULL``.

Revision ID: x5a7c9e1g3i5
Revises: w4z6b8d0f2h4
Create Date: 2026-05-14 01:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "x5a7c9e1g3i5"
down_revision: str | None = "w4z6b8d0f2h4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add ``source_entity_kind`` + ``source_entity_ref`` columns."""
    op.execute(
        "ALTER TABLE user_notifications "
        "ADD COLUMN source_entity_kind VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE user_notifications "
        "ADD COLUMN source_entity_ref VARCHAR(500)"
    )


def downgrade() -> None:
    """Reverse: drop the two columns."""
    op.execute(
        "ALTER TABLE user_notifications DROP COLUMN source_entity_ref"
    )
    op.execute(
        "ALTER TABLE user_notifications DROP COLUMN source_entity_kind"
    )
