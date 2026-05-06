"""SQLite-side FTS5 layer for the audit lake.

Owns the ``audit_search`` virtual table layout, the per-source
trigger generation, the ``MATCH``-based search, and the rebuild path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from pointlessql.services.audit_fts import logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _RUNS_TEXT,
    },
    {
        "table": "agent_run_operations",
        "axis": "ops",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "IFNULL(NEW.target_table,'')",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _OPS_TEXT,
    },
    {
        "table": "query_history",
        "axis": "queries",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _QUERIES_TEXT,
    },
    {
        "table": "agent_run_tool_calls",
        "axis": "tool_calls",
        "entity_col": "id",
        "run_id_expr": "IFNULL(NEW.agent_run_id,'')",
        "principal_expr": "''",
        "table_fqn_expr": "''",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _TOOL_CALLS_TEXT,
    },
    {
        "table": "audit_log",
        "axis": "audit_log",
        "entity_col": "id",
        "run_id_expr": "''",
        "principal_expr": "IFNULL(NEW.user_email,'')",
        "table_fqn_expr": "IFNULL(NEW.target,'')",
        "workspace_id_expr": "IFNULL(NEW.workspace_id, 1)",
        "text_expr": _AUDIT_LOG_TEXT,
    },
)


_VTABLE_SQL = """
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


_INITIAL_POPULATION_SQL: tuple[str, ...] = (
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
           IFNULL(workspace_id, 1),
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
           IFNULL(workspace_id, 1),
           IFNULL(action,'') || ' ' || IFNULL(target,'') || ' ' ||
           IFNULL(detail,'') || ' ' || IFNULL(user_email,'')
    FROM audit_log
    """,
)


def _trigger_statements(spec: dict[str, str]) -> list[str]:
    """Build the three SQLite trigger statements for one source table."""
    table = spec["table"]
    axis = spec["axis"]
    entity_col = spec["entity_col"]
    run_id_expr = spec["run_id_expr"]
    principal_expr = spec["principal_expr"]
    table_fqn_expr = spec["table_fqn_expr"]
    workspace_id_expr = spec.get("workspace_id_expr", "1")
    text_expr = spec["text_expr"]
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
                {run_id_expr},
                {principal_expr},
                {table_fqn_expr},
                {workspace_id_expr},
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
                axis, entity_id, run_id, principal, table_fqn, workspace_id, text
            )
            VALUES (
                '{axis}',
                CAST(NEW.{entity_col} AS TEXT),
                {run_id_expr},
                {principal_expr},
                {table_fqn_expr},
                {workspace_id_expr},
                {text_expr}
            );
        END
        """,
    ]


def is_available(session: Session) -> bool:
    """Return ``True`` when the SQLite ``audit_search`` virtual table exists."""
    try:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_search'")
        ).first()
    except Exception:  # noqa: BLE001 — best-effort probe
        return False
    return result is not None


def search(
    session: Session,
    *,
    sanitised: str,
    axis: str,
    limit: int,
    workspace_id: int | None,
) -> list[dict[str, Any]] | None:
    """SQLite path: ``audit_search MATCH :query``."""
    if not is_available(session):
        return None

    params: dict[str, Any] = {"query": sanitised, "limit": limit}
    sql_parts: list[str] = [
        "SELECT s.axis, s.entity_id, s.run_id, s.principal, s.table_fqn, "
        "s.workspace_id, "
        "snippet(audit_search, 6, '<mark>', '</mark>', '…', 16) AS snippet, "
        "rank "
        "FROM audit_search s "
        "WHERE audit_search MATCH :query"
    ]
    if axis != "all":
        sql_parts.append("AND s.axis = :axis")
        params["axis"] = axis
    if workspace_id is not None:
        sql_parts.append("AND s.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    sql_parts.append("ORDER BY rank LIMIT :limit")
    sql = " ".join(sql_parts)

    try:
        rows = session.execute(text(sql), params).all()
    except Exception:  # noqa: BLE001 — bad MATCH syntax surfaces here
        logger.exception("audit_search MATCH failed for %r", sanitised)
        return None

    return [
        {
            "axis": row.axis,
            "entity_id": row.entity_id,
            "run_id": row.run_id or None,
            "principal": row.principal or None,
            "table_fqn": row.table_fqn or None,
            "workspace_id": int(row.workspace_id) if row.workspace_id is not None else 1,
            "snippet": row.snippet,
            "rank": float(row.rank) if row.rank is not None else None,
        }
        for row in rows
    ]


def install_index(session: Session) -> bool:
    """Create the SQLite FTS5 virtual table + triggers + initial population."""
    existing = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_search'")
    ).first()
    if existing is not None:
        return False
    session.execute(text(_VTABLE_SQL))
    for spec in _TRIGGER_SPECS:
        for stmt in _trigger_statements(spec):
            session.execute(text(stmt))
    for stmt in _INITIAL_POPULATION_SQL:
        session.execute(text(stmt))
    session.commit()
    return True


def rebuild_index(session: Session, counts: dict[str, int]) -> dict[str, int]:
    """Drop and re-seed the SQLite FTS index from the source tables."""
    session.execute(text("DELETE FROM audit_search"))
    for stmt in _INITIAL_POPULATION_SQL:
        session.execute(text(stmt))
    for axis_name in counts:
        count_value = (
            session.execute(
                text("SELECT COUNT(*) FROM audit_search WHERE axis = :axis"),
                {"axis": axis_name},
            ).scalar()
            or 0
        )
        counts[axis_name] = int(count_value)
    session.commit()
    return counts
