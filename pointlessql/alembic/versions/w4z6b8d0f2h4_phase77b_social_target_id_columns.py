"""phase77 — social_target_id columns on the seven DP-social tables

Adds the nullable ``social_target_id INTEGER`` column + FK to
``social_targets.id`` on the seven existing Phase-76 social
tables, then backfills every row by joining through the
``social_targets`` anchor rows the prior 77.0.A migration
created (one per existing DP).

Tables touched:

* ``data_product_comments``
* ``data_product_reviews``
* ``data_product_endorsements``
* ``data_product_follows``
* ``data_product_reactions``
* ``data_product_comment_reactions``
* ``data_product_readmes``

Strategy: nullable in this revision; the dual-write phase of
Phase 77.0 (chunks C / F) makes every new social INSERT carry
both ``data_product_id`` and ``social_target_id``; the
``data_product_id`` column itself is dropped in 77.0.G (a later
revision) and ``social_target_id`` flipped to NOT NULL at that
point.  Keeping the column nullable here lets the legacy DP
routes keep writing rows without crashing while the rest of the
77.0 plumbing rolls out.

Revision ID: w4z6b8d0f2h4
Revises: v3y5a7c9e1g3
Create Date: 2026-05-14 00:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "w4z6b8d0f2h4"
down_revision: str | None = "v3y5a7c9e1g3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_WITH_DP_FK: tuple[str, ...] = (
    "data_product_comments",
    "data_product_reviews",
    "data_product_endorsements",
    "data_product_follows",
    "data_product_reactions",
    "data_product_comment_reactions",
    "data_product_readmes",
)


def upgrade() -> None:
    """Add nullable social_target_id + FK + index on 7 tables; backfill.

    Uses raw ``ALTER TABLE ADD COLUMN`` instead of
    :func:`op.add_column` because :class:`sa.ForeignKey` requires
    ALTER-of-constraints which SQLite does not support outside
    batch mode.  This matches the Phase-76.5 + 76.5.1 pattern
    (``u2w4y6a8c0e3``) for agent-authorship columns: Postgres
    honours the FK; SQLite parses it and ignores enforcement.
    The route layer is the canonical gate so the FK is defence-
    in-depth.  ``env._include_object`` skips this FK in
    ``alembic check`` via the ``social_target_id`` entry on
    :data:`_AGENT_AUTHOR_FK_COLUMNS` (renamed
    ``_SKIPPED_FK_COLUMNS`` in this revision).
    """
    for table in _TABLES_WITH_DP_FK:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN social_target_id INTEGER REFERENCES social_targets(id)"
        )
        op.create_index(
            f"ix_{table}_social_target",
            table,
            ["social_target_id"],
        )
        if table == "data_product_comment_reactions":
            # Comment-reactions piggy-back on the comment's
            # social_target — the comment has been backfilled
            # already (it appears earlier in the tuple), so its
            # ``social_target_id`` column carries the DP anchor.
            op.execute(
                """
                UPDATE data_product_comment_reactions
                SET social_target_id = (
                    SELECT c.social_target_id
                    FROM data_product_comments AS c
                    WHERE c.id = data_product_comment_reactions.comment_id
                )
                """
            )
            continue
        # Backfill: every existing row points at the anchor for
        # its DP.  ``data_product_id`` is the legacy FK column;
        # the 77.0.A backfill guaranteed one anchor per DP, so
        # this UPDATE finds a match for every existing row.
        op.execute(
            f"""
            UPDATE {table}
            SET social_target_id = (
                SELECT st.id FROM social_targets AS st
                WHERE st.entity_kind = 'dp'
                  AND st.data_product_id = {table}.data_product_id
            )
            """
        )


def downgrade() -> None:
    """Reverse: drop index + column on each table."""
    for table in reversed(_TABLES_WITH_DP_FK):
        op.drop_index(f"ix_{table}_social_target", table_name=table)
        op.execute(f"ALTER TABLE {table} DROP COLUMN social_target_id")
