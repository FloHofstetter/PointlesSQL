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

    # Sprint 30.0: Inline the FTS5 install SQL here as a snapshot
    # rather than importing from :mod:`pointlessql.services.audit_fts`.
    # At the chronological moment 28.1a runs on a fresh DB, only
    # ``agent_runs``/``agent_run_operations``/``agent_run_tool_calls``
    # have ``workspace_id`` (this migration's three FK additions);
    # ``query_history`` and ``audit_log`` get theirs in 28.1b
    # (``bb2d4f6h8j0l``).  Importing the live module would emit
    # ``IFNULL(NEW.workspace_id, 1)`` for all five axes and trip
    # "no such column" on the latter two during initial population.
    _install_fts_snapshot_sqlite(bind)


_VTABLE_SQL_28_1A = """
CREATE VIRTUAL TABLE audit_search USING fts5(
    axis UNINDEXED,
    entity_id UNINDEXED,
    run_id UNINDEXED,
    principal UNINDEXED,
    table_fqn UNINDEXED,
    workspace_id UNINDEXED,
    text,
    tokenize="unicode61 separators '._-'"
)
"""


_RUNS_TEXT_28_1A = (
    "IFNULL(NEW.id,'') || ' ' || IFNULL(NEW.principal,'') || ' ' || "
    "IFNULL(NEW.agent_id,'') || ' ' || IFNULL(NEW.status,'') || ' ' || "
    "IFNULL(NEW.denied_reason,'') || ' ' || IFNULL(NEW.tables_touched,'') || "
    "' ' || IFNULL(NEW.notebook_path,'')"
)
_OPS_TEXT_28_1A = (
    "IFNULL(NEW.op_name,'') || ' ' || IFNULL(NEW.target_table,'') || ' ' || "
    "IFNULL(NEW.error_message,'') || ' ' || IFNULL(NEW.params_json,'')"
)
_QUERIES_TEXT_28_1A = (
    "IFNULL(NEW.sql_text,'') || ' ' || IFNULL(NEW.user_email,'') || ' ' || "
    "IFNULL(NEW.read_kind,'') || ' ' || IFNULL(NEW.status,'')"
)
_TOOL_CALLS_TEXT_28_1A = (
    "IFNULL(NEW.tool_name,'') || ' ' || IFNULL(NEW.args_json,'') || ' ' || "
    "IFNULL(NEW.result_summary,'')"
)
_AUDIT_LOG_TEXT_28_1A = (
    "IFNULL(NEW.action,'') || ' ' || IFNULL(NEW.target,'') || ' ' || "
    "IFNULL(NEW.detail,'') || ' ' || IFNULL(NEW.user_email,'')"
)


_TRIGGER_SPECS_28_1A: tuple[dict[str, str], ...] = (
    {
        "table": "agent_runs",
        "axis": "runs",
        "entity_col": "id",
        "run_id_expr": "NEW.id",
        "principal_expr": "IFNULL(NEW.principal,'')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _RUNS_TEXT_28_1A,
    },
    {
        "table": "agent_run_operations",
        "axis": "ops",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "IFNULL(NEW.target_table,'')",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _OPS_TEXT_28_1A,
    },
    {
        "table": "query_history",
        "axis": "queries",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "''",
        # query_history grew workspace_id in 28.1b; this snapshot
        # uses the literal default that 28.1b will then rebuild.
        "workspace_id_expr": "1",
        "text_expr": _QUERIES_TEXT_28_1A,
    },
    {
        "table": "agent_run_tool_calls",
        "axis": "tool_calls",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "''",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _TOOL_CALLS_TEXT_28_1A,
    },
    {
        "table": "audit_log",
        "axis": "audit_log",
        "entity_col": "id",
        "run_id_expr": "''",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "IFNULL(NEW.target,'')",
        # audit_log grew workspace_id in 28.1b.
        "workspace_id_expr": "1",
        "text_expr": _AUDIT_LOG_TEXT_28_1A,
    },
)


def _trigger_statements_28_1a(spec: dict[str, str]) -> list[str]:
    table = spec["table"]
    axis = spec["axis"]
    entity_col = spec["entity_col"]
    return [
        f"""
        CREATE TRIGGER audit_search_{axis}_ai AFTER INSERT ON {table}
        BEGIN
            INSERT INTO audit_search(
                axis, entity_id, run_id, principal, table_fqn, workspace_id, text
            )
            VALUES (
                '{axis}',
                CAST(NEW.{entity_col} AS TEXT),
                {spec["run_id_expr"]},
                {spec["principal_expr"]},
                {spec["table_fqn_expr"]},
                {spec["workspace_id_expr"]},
                {spec["text_expr"]}
            );
        END
        """,
        f"""
        CREATE TRIGGER audit_search_{axis}_ad AFTER DELETE ON {table}
        BEGIN
            DELETE FROM audit_search
            WHERE axis = '{axis}' AND entity_id = CAST(OLD.{entity_col} AS TEXT);
        END
        """,
        f"""
        CREATE TRIGGER audit_search_{axis}_au AFTER UPDATE ON {table}
        BEGIN
            DELETE FROM audit_search
            WHERE axis = '{axis}' AND entity_id = CAST(OLD.{entity_col} AS TEXT);
            INSERT INTO audit_search(
                axis, entity_id, run_id, principal, table_fqn, workspace_id, text
            )
            VALUES (
                '{axis}',
                CAST(NEW.{entity_col} AS TEXT),
                {spec["run_id_expr"]},
                {spec["principal_expr"]},
                {spec["table_fqn_expr"]},
                {spec["workspace_id_expr"]},
                {spec["text_expr"]}
            );
        END
        """,
    ]


_INITIAL_POPULATION_SQL_28_1A: tuple[str, ...] = (
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text
    )
    SELECT 'runs', id, id, IFNULL(principal,''), '',
           IFNULL(workspace_id, 1),
           IFNULL(id,'') || ' ' || IFNULL(principal,'') || ' ' ||
           IFNULL(agent_id,'') || ' ' || IFNULL(status,'') || ' ' ||
           IFNULL(denied_reason,'') || ' ' || IFNULL(tables_touched,'') || ' ' ||
           IFNULL(notebook_path,'')
    FROM agent_runs
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text
    )
    SELECT 'ops', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', IFNULL(target_table,''),
           IFNULL(workspace_id, 1),
           IFNULL(op_name,'') || ' ' || IFNULL(target_table,'') || ' ' ||
           IFNULL(error_message,'') || ' ' || IFNULL(params_json,'')
    FROM agent_run_operations
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text
    )
    SELECT 'queries', CAST(id AS TEXT), IFNULL(agent_run_id,''), IFNULL(user_email,''), '',
           1,
           IFNULL(sql_text,'') || ' ' || IFNULL(user_email,'') || ' ' ||
           IFNULL(read_kind,'') || ' ' || IFNULL(status,'')
    FROM query_history
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text
    )
    SELECT 'tool_calls', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', '',
           IFNULL(workspace_id, 1),
           IFNULL(tool_name,'') || ' ' || IFNULL(args_json,'') || ' ' ||
           IFNULL(result_summary,'')
    FROM agent_run_tool_calls
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text
    )
    SELECT 'audit_log', CAST(id AS TEXT), '', IFNULL(user_email,''), IFNULL(target,''),
           1,
           IFNULL(action,'') || ' ' || IFNULL(target,'') || ' ' ||
           IFNULL(detail,'') || ' ' || IFNULL(user_email,'')
    FROM audit_log
    """,
)


def _install_fts_snapshot_sqlite(bind: object) -> None:
    """Install the audit_search FTS5 vtable using the 28.1a snapshot."""
    bind.execute(sa.text(_VTABLE_SQL_28_1A))  # type: ignore[attr-defined]
    for spec in _TRIGGER_SPECS_28_1A:
        for stmt in _trigger_statements_28_1a(spec):
            bind.execute(sa.text(stmt))  # type: ignore[attr-defined]
    for stmt in _INITIAL_POPULATION_SQL_28_1A:
        bind.execute(sa.text(stmt))  # type: ignore[attr-defined]


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
