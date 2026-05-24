"""phase77 — polymorphic-write enablement on the seven social tables

Phase 77.0.G makes the social-write path polymorphic without
dropping the legacy ``data_product_id`` column.  Two coordinated
schema changes per affected table:

* ``social_target_id`` is flipped from ``NULL`` to ``NOT NULL`` so
  every social row carries the polymorphic anchor.  All callers
  (DP route handlers — 77.0.F.1; new ``/api/social`` router —
  77.0.F.2; Active-Reviewer service — 77.0.F.3) already write the
  column; the pre-flight assertion guards against rows leaking
  through that legacy path.
* ``data_product_id`` is flipped to ``NULL`` so 77.1+ rows of
  ``entity_kind != 'dp'`` can leave the legacy back-pointer
  empty.  Existing ``WHERE data_product_id = :dp_id`` reader
  queries continue working untouched — they automatically scope
  to ``kind='dp'`` rows because non-dp inserts arrive with
  ``data_product_id = NULL``.

The full column-drop (locked decision #1 step 3) is deferred to
Phase 77.11 once every reader site has been swapped to query via
the ``social_targets`` anchor instead of the legacy column.
Dropping is a separate operation from enabling polymorphic
writes — splitting keeps the autonomous landing surface small.

Tables touched (in order):

* ``data_product_comments``
* ``data_product_reviews``
* ``data_product_endorsements``
* ``data_product_follows``
* ``data_product_reactions``
* ``data_product_comment_reactions`` (no ``data_product_id``
  column — only ``social_target_id`` flips to NOT NULL)
* ``data_product_readmes``

Revision ID: y6b8d0f2h4j6
Revises: x5a7c9e1g3i5
Create Date: 2026-05-14 14:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "y6b8d0f2h4j6"
down_revision: str | None = "x5a7c9e1g3i5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_WITH_DP_FK: tuple[str, ...] = (
    "data_product_comments",
    "data_product_reviews",
    "data_product_endorsements",
    "data_product_reactions",
    "data_product_readmes",
)
_TABLE_WITHOUT_DP_FK: str = "data_product_comment_reactions"
# Follows carries ``data_product_id`` as part of its composite
# PK ``(workspace_id, data_product_id, user_id)``, so the column
# cannot be NULLed without restructuring the PK.  Phase 77.0.G
# scope flips ``social_target_id`` to NOT NULL there; non-dp
# follow primitives land in a separate polymorphic ``social_stars``
# / ``social_follows`` table in 77.8 / later sub-phase.
_TABLE_WITH_DP_FK_PK: str = "data_product_follows"


def _assert_no_null_anchors(connection: sa.Connection) -> None:
    """Pre-flight: every social row must already carry social_target_id.

    77.0.F.1 / F.2 / F.3 swapped every writer; a NULL anchor at
    this point is a bug elsewhere.  Fail loudly here rather than
    silently violate the new NOT NULL.

    Args:
        connection: Active alembic connection used for the count
            queries.

    Raises:
        RuntimeError: When any social table contains rows missing
            the ``social_target_id`` back-pointer.
    """
    tables = (*_TABLES_WITH_DP_FK, _TABLE_WITHOUT_DP_FK, _TABLE_WITH_DP_FK_PK)
    for table in tables:
        count = connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE social_target_id IS NULL")
        ).scalar_one()
        if int(count) > 0:
            msg = (
                f"Phase 77.0.G pre-flight: {count} rows in {table!r} "
                "still carry NULL social_target_id; back-fill 77.0.B or "
                "swap a missing writer to use get_or_create_target() before "
                "rerunning this migration"
            )
            raise RuntimeError(msg)


def upgrade() -> None:
    """Flip ``social_target_id`` NOT NULL + ``data_product_id`` NULLABLE.

    Uses :func:`op.batch_alter_table` so SQLite (which does not
    natively support ``ALTER COLUMN`` for nullability) participates
    via the table-rebuild strategy.  Postgres performs the change
    in-place.
    """
    bind = op.get_bind()
    _assert_no_null_anchors(bind)

    for table in _TABLES_WITH_DP_FK:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "social_target_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "data_product_id",
                existing_type=sa.Integer(),
                nullable=True,
            )

    with op.batch_alter_table(_TABLE_WITHOUT_DP_FK) as batch_op:
        batch_op.alter_column(
            "social_target_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    with op.batch_alter_table(_TABLE_WITH_DP_FK_PK) as batch_op:
        batch_op.alter_column(
            "social_target_id",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    """Reverse: revert both columns to the 77.0.B nullability."""
    for table in _TABLES_WITH_DP_FK:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "data_product_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "social_target_id",
                existing_type=sa.Integer(),
                nullable=True,
            )

    with op.batch_alter_table(_TABLE_WITHOUT_DP_FK) as batch_op:
        batch_op.alter_column(
            "social_target_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    with op.batch_alter_table(_TABLE_WITH_DP_FK_PK) as batch_op:
        batch_op.alter_column(
            "social_target_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
