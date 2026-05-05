"""audit_search FTS5 virtual table + triggers (Phase 18.7)

Creates a single SQLite FTS5 virtual table that indexes free-text
content across five audit-axis source tables (``agent_runs``,
``agent_run_operations``, ``query_history``,
``agent_run_tool_calls``, ``audit_log``).  Five INSERT / UPDATE /
DELETE trigger sets keep the index in sync with the source rows.

The actual SQL lives in :mod:`pointlessql.services.audit_fts` so
the same source-of-truth drives both the migration and the test
fixtures (which can't go through alembic without slowing the
suite to a crawl).

Tokenizer is ``unicode61 separators '._-'`` so UC FQNs
(``catalog.schema.table``) are searchable component-wise.

Postgres deployments skip this migration: SQLite FTS5 syntax is
not portable.  Phase 18.7's runtime path checks for the table at
query time and returns ``available=false`` on Postgres.

Revision ID: y5u7v9w1x3z5
Revises: x4t6u8v0w2y4
Create Date: 2026-05-02 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "y5u7v9w1x3z5"
down_revision: str | None = "x4t6u8v0w2y4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the FTS5 vtable + 5 trigger sets + initial population.

    Skips on non-SQLite dialects.
    """
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    # Lazy import to keep the migration importable in environments
    # where the runtime service tree isn't fully wired (e.g. fresh
    # ``alembic --help`` invocations during repo setup).
    from pointlessql.services import audit_fts

    bind.execute(text(audit_fts._VTABLE_SQL))  # pyright: ignore[reportPrivateUsage]
    for spec in audit_fts._TRIGGER_SPECS:  # pyright: ignore[reportPrivateUsage]
        for stmt in audit_fts._trigger_statements(spec):  # pyright: ignore[reportPrivateUsage]
            bind.execute(text(stmt))
    for stmt in audit_fts._INITIAL_POPULATION_SQL:  # pyright: ignore[reportPrivateUsage]
        bind.execute(text(stmt))


def downgrade() -> None:
    """Drop the triggers + the FTS5 virtual table."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log"):
        for kind in ("ai", "ad", "au"):
            op.execute(f"DROP TRIGGER IF EXISTS audit_search_{axis}_{kind}")
    op.execute("DROP TABLE IF EXISTS audit_search")
