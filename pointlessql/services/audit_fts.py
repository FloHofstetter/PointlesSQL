"""SQLite FTS5 search across the audit lake (Phase 18.7).

The Phase 18.7 alembic migration creates a single virtual table
``audit_search`` with five trigger-maintained axes (``runs``,
``ops``, ``queries``, ``tool_calls``, ``audit_log``).  This module
hides the SQL behind a small surface so the route layer doesn't
have to know about FTS5 quirks (``MATCH`` operator, ``snippet()``
escapes, the rowid → entity_id mapping).

Postgres deployments skip the migration entirely; this module's
:func:`is_available` reports the absence honestly so the route can
return ``available=false`` instead of crashing.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

Axis = Literal["runs", "ops", "queries", "tool_calls", "audit_log", "all"]
VALID_AXES: frozenset[str] = frozenset(
    {"runs", "ops", "queries", "tool_calls", "audit_log", "all"}
)


def _is_sqlite(session: Session) -> bool:
    """Return ``True`` when the session's bind is SQLite."""
    return bool(session.bind is not None and session.bind.dialect.name == "sqlite")


def is_available(factory: sessionmaker[Session]) -> bool:
    """Report whether the ``audit_search`` virtual table exists.

    The Phase-18.7 alembic migration only runs on SQLite, so
    Postgres callers always see ``False``.  On SQLite the absence
    of the table indicates the migration hasn't been applied yet
    (e.g. a fresh test database where :func:`Base.metadata.create_all`
    skipped the FTS5 vtable because it isn't a SQLAlchemy ORM
    table).

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``True`` when the table is present and queryable.
    """
    with factory() as session:
        if not _is_sqlite(session):
            return False
        try:
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_search'")
            ).first()
        except Exception:  # noqa: BLE001 — best-effort probe
            return False
        return result is not None


_FTS_RESERVED = re.compile(r'[^\w._\-\s]', re.UNICODE)


def _sanitise_query(query: str) -> str:
    """Strip FTS5 reserved punctuation from a user-supplied query.

    The default tokenizer treats ``.``/``_``/``-`` as separators,
    so they survive; everything else that could confuse the
    parser (parens, double quotes, asterisk) is replaced by space.
    """
    return _FTS_RESERVED.sub(" ", query).strip()


def search(
    factory: sessionmaker[Session],
    *,
    query: str,
    axis: Axis = "all",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Search the audit lake; returns a JSON-shaped result dict.

    Args:
        factory: SQLAlchemy session factory.
        query: Free-text query.  Sanitised before forwarding to
            FTS5 — bare words and dot/underscore/hyphen-glued
            tokens (``catalog.schema.table``) are kept; reserved
            FTS5 punctuation is space-replaced.
        axis: Restrict to a single axis (``runs``/``ops``/
            ``queries``/``tool_calls``/``audit_log``) or ``all``.
        since: Optional ISO-aware lower bound on the source row's
            primary timestamp.  Implemented per-axis via a JOIN
            because FTS5 itself stores no timestamp.
        until: Optional upper bound (exclusive).
        limit: Max rows returned (``rank``-ascending → most
            relevant first).

    Returns:
        ``{"available": bool, "query", "axis", "since", "until",
        "limit", "results": [...], "total_count": int}``.
        When ``available`` is ``False`` the result list is empty
        and the caller should surface "FTS not provisioned" copy.

    Raises:
        ValueError: ``axis`` is outside :data:`VALID_AXES`.
    """
    if axis not in VALID_AXES:
        raise ValueError(f"unknown axis: {axis!r}")

    response: dict[str, Any] = {
        "available": False,
        "query": query,
        "axis": axis,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "limit": limit,
        "results": [],
        "total_count": 0,
    }
    sanitised = _sanitise_query(query)
    if not sanitised:
        return response

    with factory() as session:
        if not _is_sqlite(session):
            return response
        if not is_available(factory):
            return response

        params: dict[str, Any] = {"query": sanitised, "limit": limit}
        sql_parts: list[str] = [
            "SELECT s.axis, s.entity_id, s.run_id, s.principal, s.table_fqn, "
            "snippet(audit_search, 5, '<mark>', '</mark>', '…', 16) AS snippet, "
            "rank "
            "FROM audit_search s "
            "WHERE audit_search MATCH :query"
        ]
        if axis != "all":
            sql_parts.append("AND s.axis = :axis")
            params["axis"] = axis
        sql_parts.append("ORDER BY rank LIMIT :limit")
        sql = " ".join(sql_parts)

        try:
            rows = session.execute(text(sql), params).all()
        except Exception:  # noqa: BLE001 — bad MATCH syntax surfaces here
            logger.exception("audit_search MATCH failed for %r", sanitised)
            return response

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "axis": row.axis,
                    "entity_id": row.entity_id,
                    "run_id": row.run_id or None,
                    "principal": row.principal or None,
                    "table_fqn": row.table_fqn or None,
                    "snippet": row.snippet,
                    "rank": float(row.rank) if row.rank is not None else None,
                }
            )

        if since is not None or until is not None:
            results = _apply_time_filter(session, results, since=since, until=until)

        response.update(
            {
                "available": True,
                "results": results,
                "total_count": len(results),
            }
        )
    return response


_AXIS_TIMESTAMP_QUERY: dict[str, str] = {
    "runs": (
        "SELECT id AS entity_id, started_at "
        "FROM agent_runs WHERE id IN :ids"
    ),
    "ops": (
        "SELECT CAST(id AS TEXT) AS entity_id, started_at "
        "FROM agent_run_operations WHERE id IN :ids"
    ),
    "queries": (
        "SELECT CAST(id AS TEXT) AS entity_id, started_at "
        "FROM query_history WHERE id IN :ids"
    ),
    "tool_calls": (
        "SELECT CAST(id AS TEXT) AS entity_id, called_at AS started_at "
        "FROM agent_run_tool_calls WHERE id IN :ids"
    ),
    "audit_log": (
        "SELECT CAST(id AS TEXT) AS entity_id, created_at AS started_at "
        "FROM audit_log WHERE id IN :ids"
    ),
}


def _apply_time_filter(
    session: Session,
    rows: list[dict[str, Any]],
    *,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
) -> list[dict[str, Any]]:
    """Drop rows whose source-table timestamp is outside ``[since, until)``.

    FTS5 indexes only the ``text`` corpus, so timestamp filtering
    has to JOIN back per axis.  We bucket the candidates by axis,
    look the timestamps up in one query per axis, and filter in
    Python.
    """
    by_axis: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_axis.setdefault(row["axis"], []).append(row)
    out: list[dict[str, Any]] = []
    for axis, axis_rows in by_axis.items():
        sql = _AXIS_TIMESTAMP_QUERY.get(axis)
        if sql is None:
            out.extend(axis_rows)
            continue
        ids = [r["entity_id"] for r in axis_rows]
        if not ids:
            continue
        # ``IN :ids`` requires expanding bind params via tuple-of-values
        ts_lookup: dict[str, datetime.datetime | None] = {}
        bind_names = ",".join(f":id_{i}" for i in range(len(ids)))
        expanded_sql = sql.replace(":ids", f"({bind_names})")
        result = session.execute(
            text(expanded_sql),
            {f"id_{i}": ids[i] for i in range(len(ids))},
        )
        for record in result.all():
            entity_id = record.entity_id
            ts = record.started_at
            if ts is not None and ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.UTC)
            ts_lookup[str(entity_id)] = ts
        for row in axis_rows:
            ts = ts_lookup.get(row["entity_id"])
            if ts is None:
                out.append(row)
                continue
            if since is not None and ts < since:
                continue
            if until is not None and ts >= until:
                continue
            out.append(row)
    return out


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


def _trigger_statements(spec: dict[str, str]) -> list[str]:
    """Build the three trigger statements that keep ``audit_search`` in sync.

    Args:
        spec: Mapping with ``table``/``axis``/``entity_col``/
            ``run_id_expr``/``principal_expr``/``table_fqn_expr``/
            ``text_expr`` — see :data:`_TRIGGER_SPECS`.

    Returns:
        List of three CREATE TRIGGER statements (insert, delete,
        update).
    """
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
            INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
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
            INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
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
    INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
    SELECT 'runs', id, id, IFNULL(principal,''), '',
           IFNULL(id,'') || ' ' || IFNULL(principal,'') || ' ' ||
           IFNULL(agent_id,'') || ' ' || IFNULL(status,'') || ' ' ||
           IFNULL(denied_reason,'') || ' ' || IFNULL(tables_touched,'') || ' ' ||
           IFNULL(notebook_path,'')
    FROM agent_runs
    """,
    """
    INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
    SELECT 'ops', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', IFNULL(target_table,''),
           IFNULL(op_name,'') || ' ' || IFNULL(target_table,'') || ' ' ||
           IFNULL(error_message,'') || ' ' || IFNULL(params_json,'')
    FROM agent_run_operations
    """,
    """
    INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
    SELECT 'queries', CAST(id AS TEXT), IFNULL(agent_run_id,''), IFNULL(user_email,''), '',
           IFNULL(sql_text,'') || ' ' || IFNULL(user_email,'') || ' ' ||
           IFNULL(read_kind,'') || ' ' || IFNULL(status,'')
    FROM query_history
    """,
    """
    INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
    SELECT 'tool_calls', CAST(id AS TEXT), IFNULL(agent_run_id,''), '', '',
           IFNULL(tool_name,'') || ' ' || IFNULL(args_json,'') || ' ' ||
           IFNULL(result_summary,'')
    FROM agent_run_tool_calls
    """,
    """
    INSERT INTO audit_search(axis, entity_id, run_id, principal, table_fqn, text)
    SELECT 'audit_log', CAST(id AS TEXT), '', IFNULL(user_email,''), IFNULL(target,''),
           IFNULL(action,'') || ' ' || IFNULL(target,'') || ' ' ||
           IFNULL(detail,'') || ' ' || IFNULL(user_email,'')
    FROM audit_log
    """,
)


def install_index(factory: sessionmaker[Session]) -> bool:
    """Create the FTS5 vtable + triggers + initial population.

    Idempotent: returns ``False`` if the vtable already exists, so
    test fixtures can call this unconditionally.  SQLite-only —
    Postgres backends return ``False`` because the FTS5 syntax
    doesn't translate.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``True`` when the vtable was newly created; ``False`` when
        the backend isn't SQLite or the vtable already existed.
    """
    with factory() as session:
        if not _is_sqlite(session):
            return False
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


def rebuild_index(factory: sessionmaker[Session]) -> dict[str, int]:
    """Drop and re-seed the FTS5 index from the source tables.

    Used as an emergency-recovery hook when triggers drift
    (e.g. a manual DB edit happened outside the trigger path).
    Idempotent — multiple calls leave the index in the same state.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``{"runs": int, "ops": int, "queries": int, "tool_calls": int,
        "audit_log": int}`` row-count per axis after the rebuild.
    """
    counts: dict[str, int] = {axis: 0 for axis in VALID_AXES if axis != "all"}
    if not is_available(factory):
        return counts
    with factory() as session:
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
