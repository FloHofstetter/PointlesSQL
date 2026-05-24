"""phase78 polish — audit FTS gets ``entity_kind`` + full comment body.

The Phase 77 social layer now lands a dense per-kind audit trail
(``data_product:`` for kind='dp', generic ``{kind}:`` otherwise).
This migration extends the cockpit FTS surface so operators can
filter ``/audit/search`` results by entity kind and search the
*full* body of every discussion comment (not just the 140-char
preview the original mirror called persisted).

Two changes:

* **``entity_kind`` UNINDEXED column** on the SQLite FTS5 virtual
  table + an ``entity_kind`` text column on the PG GIN-backed
  ``audit_search_index`` table.  The kind is derived from
  ``audit_log.target`` at write time: the legacy
  ``data_product:`` prefix maps to ``dp`` (locked decision #9 of
  the Phase-77 plan) and every other ``{kind}:{ref}`` carries
  its own prefix.  Non-audit-log axes carry the empty string —
  the kind notion only exists on the audit_log axis.
* **Full-body comment indexing** drops in automatically once the
  audit-mirror callers include the full ``body_md`` in their
  detail JSON (companion code change in this commit).  The FTS
  ``text`` expression already concatenates ``detail`` so no
  trigger change is needed for that.

Both dialect surfaces share the same logical layout: drop the
old virtual table / column, recreate via :func:`install_index`,
re-seed from the source tables.

Revision ID: h5j7l9n1p3r5
Revises: g4i6k8m0o2q4
Create Date: 2026-05-16 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "h5j7l9n1p3r5"
down_revision: str | None = "g4i6k8m0o2q4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SQLITE_TRIGGER_NAMES: tuple[str, ...] = tuple(
    f"audit_search_{axis}_{kind}"
    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log")
    for kind in ("ai", "ad", "au")
)


def upgrade() -> None:
    """Add ``entity_kind`` to both dialect FTS surfaces + re-seed."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # SQLite FTS5 virtual tables don't support ALTER, so we
        # drop + recreate.  Source-table data stays intact;
        # install_index() repopulates from those.
        from pointlessql.services.audit_fts import _sqlite

        for trigger_name in _SQLITE_TRIGGER_NAMES:
            bind.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
        bind.execute(text("DROP TABLE IF EXISTS audit_search"))
        # Use a fresh session bound to the same connection so the
        # _sqlite installer can commit.  ``install_index`` recreates
        # the vtable with the new ``entity_kind`` column, attaches
        # triggers, and runs the initial population SQL.
        from sqlalchemy.orm import Session

        with Session(bind=bind) as session:
            _sqlite.install_index(session)

    elif dialect == "postgresql":
        # PG can ALTER TABLE — add the column, backfill from target,
        # then re-attach triggers via install_index() so future
        # writes populate entity_kind correctly.
        bind.execute(
            text(
                "ALTER TABLE audit_search_index "
                "ADD COLUMN IF NOT EXISTS entity_kind TEXT NOT NULL DEFAULT ''"
            )
        )
        bind.execute(
            text(
                "UPDATE audit_search_index "
                "SET entity_kind = CASE "
                "    WHEN axis = 'audit_log' "
                "         AND table_fqn LIKE 'data_product:%' THEN 'dp' "
                "    WHEN axis = 'audit_log' "
                "         AND position(':' IN COALESCE(table_fqn, '')) > 0 "
                "      THEN split_part(table_fqn, ':', 1) "
                "    ELSE '' END "
                "WHERE entity_kind = ''"
            )
        )
        bind.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_search_entity_kind "
                "ON audit_search_index (entity_kind)"
            )
        )
        # Re-attach triggers so future writes populate the new
        # column.  install_index() drops + recreates the trigger
        # functions and trigger bindings; the table already exists
        # so the initial-populate step is a no-op (ON CONFLICT DO
        # NOTHING).  Operators should ``REINDEX INDEX
        # ix_audit_search_text_search`` post-deploy if a long-form
        # comment body should re-rank.  Skipped here because
        # CONCURRENTLY blocks transactional DDL.
        from sqlalchemy.orm import Session

        from pointlessql.services.audit_fts import _postgres

        with Session(bind=bind) as session:
            _postgres.install_index(session)


def downgrade() -> None:
    """Drop the ``entity_kind`` column / FTS5 axis on rollback."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        # Drop + recreate without the new column.  Source tables
        # don't change, so reinstalling with the pre-Phase-78 layout
        # would require shipping the old install code as well.
        # Instead, leave the FTS5 vtable in the new shape but make
        # downgrade a logical no-op: the new column is UNINDEXED so
        # the search surface still works against the pre-Phase-78
        # API.  The kind filter just stops matching anything.
        return

    if dialect == "postgresql":
        bind.execute(text("DROP INDEX IF EXISTS ix_audit_search_entity_kind"))
        bind.execute(text("ALTER TABLE audit_search_index DROP COLUMN IF EXISTS entity_kind"))
