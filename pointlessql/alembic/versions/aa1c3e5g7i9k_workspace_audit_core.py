"""workspace_id on audit-trail core (agent_runs + agent_run_*) + FTS surgery (Phase 28.1a)

Sprint 28.1a — adds the workspace_id FK to the five audit-trail
source tables and rebuilds the SQLite FTS5 ``audit_search``
virtual table to carry workspace_id as a UNINDEXED column.

After this migration a workspace-A user CANNOT see workspace-B's
agent runs, source bytes, operations, lifecycle events, tool
calls, or full-text search hits scoped via the workspace filter.

Tables touched:

* ``agent_runs.workspace_id`` (NOT NULL with server_default='1')
* ``agent_run_sources.workspace_id`` (NOT NULL, server_default='1')
* ``agent_run_operations.workspace_id`` (NOT NULL, server_default='1')
* ``agent_run_events.workspace_id`` (NOT NULL, server_default='1')
* ``agent_run_tool_calls.workspace_id`` (NOT NULL, server_default='1')

Indexes added:

* ``ix_agent_runs_workspace_started`` on ``(workspace_id, started_at)``
* ``ix_agent_run_sources_workspace_run`` on ``(workspace_id, agent_run_id)``
* ``ix_agent_run_operations_workspace_run`` on ``(workspace_id, agent_run_id)``
* ``ix_agent_run_events_workspace_run`` on ``(workspace_id, agent_run_id)``
* ``ix_agent_run_tool_calls_workspace_run`` on ``(workspace_id, agent_run_id)``

FTS5 surgery: SQLite FTS5 doesn't support ``ALTER TABLE … ADD COLUMN``
on virtual tables.  The migration drops the existing 15 triggers + the
``audit_search`` vtable and re-runs :func:`audit_fts.install_index`
which recreates the vtable with the new ``workspace_id UNINDEXED``
column (sixth slot, before ``text``) plus the trigger set populating
it.  Cheap because the index is fresh from Sprint 18.7.

``query_history`` and ``audit_log`` source tables haven't gained the
``workspace_id`` column yet (they land in Sprint 28.1b); their FTS
trigger specs emit literal ``1`` until 28.1b flips them to
``IFNULL(NEW.workspace_id, 1)``.  All existing rows therefore stay
visible in default-workspace searches without code change.

Postgres deployments: only the workspace_id column adds run; the
FTS5 surgery is a no-op (the vtable doesn't exist on Postgres).

Revision ID: aa1c3e5g7i9k
Revises: z6w8a0b2c4d6
Create Date: 2026-05-05 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa1c3e5g7i9k"
down_revision: str | None = "z6w8a0b2c4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_AND_INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "agent_runs",
        "ix_agent_runs_workspace_started",
        ["workspace_id", "started_at"],
    ),
    (
        "agent_run_sources",
        "ix_agent_run_sources_workspace_run",
        ["workspace_id", "agent_run_id"],
    ),
    (
        "agent_run_operations",
        "ix_agent_run_operations_workspace_run",
        ["workspace_id", "agent_run_id"],
    ),
    (
        "agent_run_events",
        "ix_agent_run_events_workspace_run",
        ["workspace_id", "agent_run_id"],
    ),
    (
        "agent_run_tool_calls",
        "ix_agent_run_tool_calls_workspace_run",
        ["workspace_id", "agent_run_id"],
    ),
)


def upgrade() -> None:
    """Add workspace_id columns + indexes; rebuild FTS5 vtable."""
    bind = op.get_bind()

    # 1. workspace_id on every audit-trail core table -----------------------
    for table_name, _index_name, _index_cols in _TABLES_AND_INDEXES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "workspace_id",
                    sa.Integer(),
                    sa.ForeignKey("workspaces.id", name=f"fk_{table_name}_workspace_id"),
                    nullable=False,
                    server_default="1",
                )
            )

    # 2. Belt-and-braces backfill (server_default already filled rows; this
    #    catches any historic NULLs from manual DB edits).
    for table_name, _, _ in _TABLES_AND_INDEXES:
        bind.execute(
            sa.text(f"UPDATE {table_name} SET workspace_id = 1 WHERE workspace_id IS NULL")
        )

    # 3. Compound indexes ---------------------------------------------------
    for table_name, index_name, index_cols in _TABLES_AND_INDEXES:
        op.create_index(index_name, table_name, index_cols)

    # 4. FTS5 vtable rebuild (SQLite only) ----------------------------------
    if bind.dialect.name != "sqlite":
        return

    # Drop the existing 15 triggers + the vtable so install_index() can
    # recreate it with the new workspace_id column.
    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log"):
        for kind in ("ai", "ad", "au"):
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_{kind}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS audit_search"))

    # Re-run install_index against the migration's bind by importing the
    # SQL templates directly — the same pattern the Sprint 18.7 migration
    # uses to keep one source of truth for the vtable definition.
    from pointlessql.services import audit_fts

    bind.execute(sa.text(audit_fts._VTABLE_SQL))  # pyright: ignore[reportPrivateUsage]
    for spec in audit_fts._TRIGGER_SPECS:  # pyright: ignore[reportPrivateUsage]
        for stmt in audit_fts._trigger_statements(spec):  # pyright: ignore[reportPrivateUsage]
            bind.execute(sa.text(stmt))
    for stmt in audit_fts._INITIAL_POPULATION_SQL:  # pyright: ignore[reportPrivateUsage]
        bind.execute(sa.text(stmt))


def downgrade() -> None:
    """Drop indexes + workspace_id columns; rebuild FTS5 vtable on the old shape."""
    bind = op.get_bind()

    for table_name, index_name, _ in _TABLES_AND_INDEXES:
        op.drop_index(index_name, table_name=table_name)
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("workspace_id")

    if bind.dialect.name != "sqlite":
        return

    # Drop the new vtable + triggers.  We don't recreate the old (no
    # workspace_id) vtable here — downgrade is best-effort and the
    # operational story is "roll forward, not back".  Anyone needing
    # the index can re-run ``services.audit_fts.install_index`` after
    # downgrade.
    for axis in ("runs", "ops", "queries", "tool_calls", "audit_log"):
        for kind in ("ai", "ad", "au"):
            bind.execute(sa.text(f"DROP TRIGGER IF EXISTS audit_search_{axis}_{kind}"))
    bind.execute(sa.text("DROP TABLE IF EXISTS audit_search"))
