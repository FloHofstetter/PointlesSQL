"""audit_search FTS5 virtual table + triggers

Creates a single SQLite FTS5 virtual table that indexes free-text
content across five audit-axis source tables (``agent_runs``,
``agent_run_operations``, ``query_history``,
``agent_run_tool_calls``, ``audit_log``).  Five INSERT / UPDATE /
DELETE trigger sets keep the index in sync with the source rows.

The vtable + trigger SQL is **inlined** here rather than imported
from :mod:`pointlessql.services.audit_fts`.  The Phase-28.1a
``aa1c3e5g7i9k`` migration adds ``workspace_id`` to the audit-trail
core tables and rebuilds the FTS index with the new column —
inlining the original workspace-less shape here keeps this
migration replayable on a fresh DB even after the live module
moved on (Sprint 30.0 would otherwise fail on ``no such column:
workspace_id`` because the SELECT in initial-population is parsed
against the schema state at migration runtime, not at row-insert
time).

Tokenizer is ``unicode61 separators '._-'`` so UC FQNs
(``catalog.schema.table``) are searchable component-wise.

Postgres deployments skip this migration entirely.  Sprint 30.1's
``hh8j0l2n4p6r`` migration installs the equivalent
``audit_search_index`` table (tsvector + GIN) for Postgres.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-02 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VTABLE_SQL = """
CREATE VIRTUAL TABLE audit_search USING fts5(
    axis UNINDEXED,
    entity_id UNINDEXED,
    run_id UNINDEXED,
    principal UNINDEXED,
    table_fqn UNINDEXED,
    text,
    tokenize="unicode61 separators '._-'"
)
"""


_RUNS_TEXT = (
    "IFNULL(NEW.id,'') || ' ' || IFNULL(NEW.principal,'') || ' ' || "
    "IFNULL(NEW.agent_id,'') || ' ' || IFNULL(NEW.status,'') || ' ' || "
    "IFNULL(NEW.denied_reason,'') || ' ' || IFNULL(NEW.tables_touched,'') || "
    "' ' || IFNULL(NEW.notebook_path,'')"
)
_OPS_TEXT = (
    "IFNULL(NEW.op_name,'') || ' ' || IFNULL(NEW.target_table,'') || ' ' || "
    "IFNULL(NEW.error_message,'') || ' ' || IFNULL(NEW.params_json,'')"
)
_QUERIES_TEXT = (
    "IFNULL(NEW.sql_text,'') || ' ' || IFNULL(NEW.user_email,'') || ' ' || "
    "IFNULL(NEW.read_kind,'') || ' ' || IFNULL(NEW.status,'')"
)
_TOOL_CALLS_TEXT = (
    "IFNULL(NEW.tool_name,'') || ' ' || IFNULL(NEW.args_json,'') || ' ' || "
    "IFNULL(NEW.result_summary,'')"
)
_AUDIT_LOG_TEXT = (
    "IFNULL(NEW.action,'') || ' ' || IFNULL(NEW.target,'') || ' ' || "
    "IFNULL(NEW.detail,'') || ' ' || IFNULL(NEW.user_email,'')"
)


_TRIGGER_SPECS: tuple[dict[str, str], ...] = (
    {
        "table": "agent_runs",
        "axis": "runs",
        "entity_col": "id",
        "run_id_expr": "NEW.id",
        "principal_expr": "IFNULL(NEW.principal,'')",
        "table_fqn_expr": "''",
        "text_expr": _RUNS_TEXT,
    },
    {
        "table": "agent_run_operations",
        "axis": "ops",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "IFNULL(NEW.target_table,'')",
        "text_expr": _OPS_TEXT,
    },
    {
        "table": "query_history",
        "axis": "queries",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "''",
        "text_expr": _QUERIES_TEXT,
    },
    {
        "table": "agent_run_tool_calls",
        "axis": "tool_calls",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "''",
        "text_expr": _TOOL_CALLS_TEXT,
    },
    {
        "table": "audit_log",
        "axis": "audit_log",
        "entity_col": "id",
        "run_id_expr": "''",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "IFNULL(NEW.target,'')",
        "text_expr": _AUDIT_LOG_TEXT,
    },
)


def _trigger_statements(spec: dict[str, str]) -> list[str]:
    """Build the three SQLite trigger statements for one source table."""
    table = spec["table"]
    axis = spec["axis"]
    entity_col = spec["entity_col"]
    run_id_expr = spec["run_id_expr"]
    principal_expr = spec["principal_expr"]
    table_fqn_expr = spec["table_fqn_expr"]
    text_expr = spec["text_expr"]
    return [
        f"""
        CREATE TRIGGER audit_search_{axis}_ai AFTER INSERT ON {table}
        BEGIN
            INSERT INTO audit_search(
                axis, entity_id, run_id, principal, table_fqn, text
            )
            VALUES (
                '{axis}',
                CAST(NEW.{entity_col} AS TEXT),
                {run_id_expr},
                {principal_expr},
                {table_fqn_expr},
                {text_expr}
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
                axis, entity_id, run_id, principal, table_fqn, text
            )
            VALUES (
                '{axis}',
                CAST(NEW.{entity_col} AS TEXT),
                {run_id_expr},
                {principal_expr},
                {table_fqn_expr},
                {text_expr}
            );
        END
        """,
    ]


_INITIAL_POPULATION_SQL: tuple[str, ...] = (
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, text
    )
    SELECT 'runs', id, id, IFNULL(principal,''), '',
           IFNULL(id,'') || ' ' || IFNULL(principal,'') || ' ' ||
           IFNULL(agent_id,'') || ' ' || IFNULL(status,'') || ' ' ||
           IFNULL(denied_reason,'') || ' ' || IFNULL(tables_touched,'') || ' ' ||
           IFNULL(notebook_path,'')
    FROM agent_runs
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, text
    )
    SELECT 'ops', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', IFNULL(target_table,''),
           IFNULL(op_name,'') || ' ' || IFNULL(target_table,'') || ' ' ||
           IFNULL(error_message,'') || ' ' || IFNULL(params_json,'')
    FROM agent_run_operations
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, text
    )
    SELECT 'queries', CAST(id AS TEXT), IFNULL(agent_run_id,''), IFNULL(user_email,''), '',
           IFNULL(sql_text,'') || ' ' || IFNULL(user_email,'') || ' ' ||
           IFNULL(read_kind,'') || ' ' || IFNULL(status,'')
    FROM query_history
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, text
    )
    SELECT 'tool_calls', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', '',
           IFNULL(tool_name,'') || ' ' || IFNULL(args_json,'') || ' ' ||
           IFNULL(result_summary,'')
    FROM agent_run_tool_calls
    """,
    """
    INSERT INTO audit_search(
        axis, entity_id, run_id, principal, table_fqn, text
    )
    SELECT 'audit_log', CAST(id AS TEXT), '', IFNULL(user_email,''), IFNULL(target,''),
           IFNULL(action,'') || ' ' || IFNULL(target,'') || ' ' ||
           IFNULL(detail,'') || ' ' || IFNULL(user_email,'')
    FROM audit_log
    """,
)


def upgrade() -> None:
    """Create the FTS5 vtable + 5 trigger sets + initial population.

    Skips on non-SQLite dialects.  The SQL is inlined here (not
    imported from :mod:`pointlessql.services.audit_fts`) so the
    migration replays correctly on a fresh DB regardless of how the
    live module evolves later.
    """
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    bind.execute(text(_VTABLE_SQL))
    for spec in _TRIGGER_SPECS:
        for stmt in _trigger_statements(spec):
            bind.execute(text(stmt))
    for stmt in _INITIAL_POPULATION_SQL:
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
