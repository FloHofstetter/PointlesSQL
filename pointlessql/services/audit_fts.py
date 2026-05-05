"""Free-text search across the audit lake.

The audit cockpit's ``GET /api/audit/search`` is dialect-portable
since Sprint 30.1: a SQLite FTS5 virtual table on SQLite, a
Postgres ``tsvector + GIN`` index on Postgres, both hidden behind
the same :func:`search` entry point so the route layer doesn't
have to care about backend specifics.

Layout summary:

* SQLite — Phase-18.7 alembic ``y5u7v9w1x3z5`` creates a single
  ``audit_search`` virtual table with five trigger-maintained
  axes (``runs``, ``ops``, ``queries``, ``tool_calls``,
  ``audit_log``).
* Postgres — Sprint-30.1 alembic ``hh8j0l2n4p6r`` creates an
  ``audit_search_index`` table with a GIN index over a generated
  ``tsvector`` column, fed by five PL/pgSQL trigger functions.

Both surfaces return the same ``(axis, entity_id, run_id,
principal, table_fqn, workspace_id, snippet, rank)`` rowshape so
templates and the plugin's audit-search tool render identically.
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
VALID_AXES: frozenset[str] = frozenset({"runs", "ops", "queries", "tool_calls", "audit_log", "all"})


def _dialect(session: Session) -> str:
    """Return the dialect name of the session's bound engine."""
    return session.bind.dialect.name if session.bind is not None else ""


def _is_sqlite(session: Session) -> bool:
    """Return ``True`` when the session's bind is SQLite."""
    return _dialect(session) == "sqlite"


def _is_postgres(session: Session) -> bool:
    """Return ``True`` when the session's bind is PostgreSQL."""
    return _dialect(session) == "postgresql"


def is_available(factory: sessionmaker[Session]) -> bool:
    """Report whether the FTS surface is provisioned for the current backend.

    SQLite checks for the ``audit_search`` virtual table; Postgres
    checks for the ``audit_search_index`` regular table.  Other
    backends (or unbound sessions) honestly answer ``False``.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``True`` when the FTS surface is queryable.
    """
    with factory() as session:
        if _is_sqlite(session):
            return _is_available_sqlite(session)
        if _is_postgres(session):
            return _is_available_postgres(session)
        return False


def _is_available_sqlite(session: Session) -> bool:
    try:
        result = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_search'")
        ).first()
    except Exception:  # noqa: BLE001 — best-effort probe
        return False
    return result is not None


def _is_available_postgres(session: Session) -> bool:
    try:
        result = session.execute(
            text("SELECT to_regclass('public.audit_search_index') IS NOT NULL AS exists")
        ).first()
    except Exception:  # noqa: BLE001 — best-effort probe
        return False
    return bool(result and result[0])


_FTS_RESERVED = re.compile(r"[^\w._\-\s]", re.UNICODE)


def _sanitise_query(query: str) -> str:
    """Strip FTS-reserved punctuation from a user-supplied query.

    Both backends use the same sanitiser so cross-dialect behaviour
    matches.  The default tokenizer treats ``.``/``_``/``-`` as
    safe (UC FQNs survive); everything else that could confuse the
    FTS5 parser or PG ``plainto_tsquery`` is space-replaced.
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
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Search the audit lake; returns a JSON-shaped result dict.

    Args:
        factory: SQLAlchemy session factory.
        query: Free-text query.  Sanitised before forwarding.
        axis: Restrict to a single axis or ``all``.
        since: Optional ISO-aware lower bound on the source row's
            primary timestamp.
        until: Optional upper bound (exclusive).
        limit: Max rows returned (``rank``-ordered, most relevant
            first).
        workspace_id: Phase 28 — restrict to a single workspace's
            audit corpus.  ``None`` skips the filter (super-admin
            cross-workspace lens).

    Returns:
        ``{"available", "query", "axis", "since", "until", "limit",
        "workspace_id", "results", "total_count"}``.

    Raises:
        ValueError: ``axis`` outside :data:`VALID_AXES`.
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
        "workspace_id": workspace_id,
        "results": [],
        "total_count": 0,
    }
    sanitised = _sanitise_query(query)
    if not sanitised:
        return response

    with factory() as session:
        if _is_sqlite(session):
            results = _search_sqlite(
                session,
                sanitised=sanitised,
                axis=axis,
                limit=limit,
                workspace_id=workspace_id,
            )
        elif _is_postgres(session):
            results = _search_postgres(
                session,
                sanitised=sanitised,
                axis=axis,
                limit=limit,
                workspace_id=workspace_id,
            )
        else:
            return response

        if results is None:
            return response

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


def _search_sqlite(
    session: Session,
    *,
    sanitised: str,
    axis: Axis,
    limit: int,
    workspace_id: int | None,
) -> list[dict[str, Any]] | None:
    """SQLite path: ``audit_search MATCH :query``."""
    if not _is_available_sqlite(session):
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


_PG_MARK_MERGE = re.compile(r"</mark>([._\-]+)<mark>")


def _merge_pg_marks(snippet: str | None) -> str | None:
    r"""Merge adjacent ``</mark>SEP<mark>`` patterns into one mark span.

    PG's ``ts_headline`` highlights individual tsquery matches.
    With Sprint-30.1's pre-replacement of ``[._@\\-]+``, a
    user-typed ``customer_marker_xyz`` matches three separate
    tokens, so the rendered snippet looks like
    ``<mark>customer</mark>_<mark>marker</mark>_<mark>xyz</mark>``.
    SQLite FTS5's ``snippet()`` returns
    ``<mark>customer_marker_xyz</mark>`` instead — the entire
    substring as one mark — because it indexes at separator-
    boundaries but renders against the original text.

    Cross-dialect parity matters for tests that grep snippets
    for ``customer_marker_xyz`` after a search; this helper
    smooths the PG output to match SQLite's by collapsing
    adjacent mark spans separated only by ``.``/``_``/``-``.
    """
    if snippet is None:
        return None
    return _PG_MARK_MERGE.sub(lambda m: m.group(1), snippet)


def _search_postgres(
    session: Session,
    *,
    sanitised: str,
    axis: Axis,
    limit: int,
    workspace_id: int | None,
) -> list[dict[str, Any]] | None:
    """Postgres path: ``text_search @@ plainto_tsquery``.

    The rank field flips orientation between backends: SQLite FTS5
    rank-ascending (lower=better), PG ``ts_rank`` higher=better.
    Callers iterate the returned list which is already sorted, so
    the API contract holds; we keep the raw value so audit-tooling
    can sort it explicitly if needed.
    """
    if not _is_available_postgres(session):
        return None

    # Mirror the index-side pre-replacement so the user query
    # tokenizes the same way as ``text_corpus`` did at insert time
    # — UC FQNs and email addresses split into searchable parts.
    pg_query = re.sub(r"[._@\-]+", " ", sanitised).strip()
    if not pg_query:
        return None
    params: dict[str, Any] = {"query": pg_query, "limit": limit}
    # ts_headline uses the *raw* ``text_corpus`` (with underscores
    # / dots intact) so the rendered snippet preserves the
    # original UC FQN / email shapes that callers and tests
    # search for.  Highlighting against the raw corpus loses the
    # ``<mark>`` wrap on tokens that only existed post-split, but
    # that's an acceptable trade for keeping the snippet
    # human-readable.
    sql_parts: list[str] = [
        "SELECT s.axis, s.entity_id, s.run_id, s.principal, s.table_fqn, "
        "       s.workspace_id, "
        "       ts_headline('simple', COALESCE(s.text_corpus, ''), "
        "                   plainto_tsquery('simple', :query), "
        "                   'StartSel=<mark>, StopSel=</mark>, "
        "                    MaxFragments=1, MaxWords=16, MinWords=4') "
        "         AS snippet, "
        "       ts_rank(s.text_search, plainto_tsquery('simple', :query)) "
        "         AS rank "
        "FROM audit_search_index s "
        "WHERE s.text_search @@ plainto_tsquery('simple', :query)"
    ]
    if axis != "all":
        sql_parts.append("AND s.axis = :axis")
        params["axis"] = axis
    if workspace_id is not None:
        sql_parts.append("AND s.workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    sql_parts.append("ORDER BY rank DESC LIMIT :limit")
    sql = " ".join(sql_parts)

    try:
        rows = session.execute(text(sql), params).all()
    except Exception:  # noqa: BLE001 — bad query surfaces here
        logger.exception("audit_search_index match failed for %r", sanitised)
        return None

    return [
        {
            "axis": row.axis,
            "entity_id": row.entity_id,
            "run_id": row.run_id or None,
            "principal": row.principal or None,
            "table_fqn": row.table_fqn or None,
            "workspace_id": int(row.workspace_id) if row.workspace_id is not None else 1,
            "snippet": _merge_pg_marks(row.snippet),
            "rank": float(row.rank) if row.rank is not None else None,
        }
        for row in rows
    ]


_AXIS_TIMESTAMP_QUERY: dict[str, str] = {
    "runs": ("SELECT id AS entity_id, started_at FROM agent_runs WHERE id IN :ids"),
    "ops": (
        "SELECT CAST(id AS TEXT) AS entity_id, started_at "
        "FROM agent_run_operations WHERE id IN :ids"
    ),
    "queries": (
        "SELECT CAST(id AS TEXT) AS entity_id, started_at FROM query_history WHERE id IN :ids"
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

    Both FTS surfaces store the indexed text; timestamp filtering
    has to JOIN back per axis.  We bucket the candidates by axis,
    look the timestamps up in one query per axis, and filter in
    Python — same shape on both backends.
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


# ---------------------------------------------------------------------------
# SQLite FTS5 layout (text + triggers + initial population)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Postgres FTS layout (functions + triggers + initial population)
# ---------------------------------------------------------------------------
_PG_AXES: tuple[str, ...] = ("runs", "ops", "queries", "tool_calls", "audit_log")

_PG_TRIGGER_SPECS: dict[str, dict[str, str]] = {
    "runs": {
        "table": "agent_runs",
        "entity_col": "id",
        "run_id_expr": "NEW.id",
        "principal_expr": "COALESCE(NEW.principal, '')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.id::text, '') || ' ' || COALESCE(NEW.principal, '') "
            "|| ' ' || COALESCE(NEW.agent_id, '') || ' ' || COALESCE(NEW.status, '') "
            "|| ' ' || COALESCE(NEW.denied_reason, '') "
            "|| ' ' || COALESCE(NEW.tables_touched, '') "
            "|| ' ' || COALESCE(NEW.notebook_path, '')"
        ),
    },
    "ops": {
        "table": "agent_run_operations",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "''",
        "table_fqn_expr": "COALESCE(NEW.target_table, '')",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.op_name, '') || ' ' || COALESCE(NEW.target_table, '') "
            "|| ' ' || COALESCE(NEW.error_message, '') "
            "|| ' ' || COALESCE(NEW.params_json, '')"
        ),
    },
    "queries": {
        "table": "query_history",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "COALESCE(NEW.user_email, '')",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.sql_text, '') || ' ' || COALESCE(NEW.user_email, '') "
            "|| ' ' || COALESCE(NEW.read_kind, '') || ' ' || COALESCE(NEW.status, '')"
        ),
    },
    "tool_calls": {
        "table": "agent_run_tool_calls",
        "entity_col": "id",
        "run_id_expr": "COALESCE(NEW.agent_run_id, '')",
        "principal_expr": "''",
        "table_fqn_expr": "''",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.tool_name, '') || ' ' || COALESCE(NEW.args_json, '') "
            "|| ' ' || COALESCE(NEW.result_summary, '')"
        ),
    },
    "audit_log": {
        "table": "audit_log",
        "entity_col": "id",
        "run_id_expr": "''",
        "principal_expr": "COALESCE(NEW.user_email, '')",
        "table_fqn_expr": "COALESCE(NEW.target, '')",
        "workspace_id_expr": "COALESCE(NEW.workspace_id, 1)",
        "text_expr": (
            "COALESCE(NEW.action, '') || ' ' || COALESCE(NEW.target, '') "
            "|| ' ' || COALESCE(NEW.detail, '') || ' ' || COALESCE(NEW.user_email, '')"
        ),
    },
}


#: The generated tsvector pre-replaces ``.`` / ``_`` / ``-`` /
#: ``@`` with spaces so PG's ``simple`` parser splits UC FQNs and
#: email addresses into searchable parts.  This mirrors the
#: SQLite FTS5 ``unicode61 separators '._-'`` tokenizer config and
#: keeps cross-dialect search behaviour consistent — without it,
#: ``alice@example.com`` would tokenize as a single email token on
#: PG but as three tokens on SQLite.
_PG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_search_index (
    axis TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    run_id TEXT,
    principal TEXT,
    table_fqn TEXT,
    workspace_id INTEGER,
    text_corpus TEXT,
    text_search TSVECTOR GENERATED ALWAYS AS
        (to_tsvector('simple',
            regexp_replace(COALESCE(text_corpus, ''), '[._@\\-]+', ' ', 'g'))) STORED,
    PRIMARY KEY (axis, entity_id)
)
"""


_PG_INITIAL_POPULATE_SQL: dict[str, str] = {
    "runs": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'runs', id::text, id, COALESCE(principal, ''), '', "
        "       COALESCE(workspace_id, 1), "
        "       COALESCE(id::text, '') || ' ' || COALESCE(principal, '') || ' ' || "
        "       COALESCE(agent_id, '') || ' ' || COALESCE(status, '') || ' ' || "
        "       COALESCE(denied_reason, '') || ' ' || COALESCE(tables_touched, '') || ' ' || "
        "       COALESCE(notebook_path, '') "
        "FROM agent_runs ON CONFLICT DO NOTHING"
    ),
    "ops": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'ops', id::text, COALESCE(agent_run_id, ''), '', "
        "       COALESCE(target_table, ''), COALESCE(workspace_id, 1), "
        "       COALESCE(op_name, '') || ' ' || COALESCE(target_table, '') || ' ' || "
        "       COALESCE(error_message, '') || ' ' || COALESCE(params_json, '') "
        "FROM agent_run_operations ON CONFLICT DO NOTHING"
    ),
    "queries": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'queries', id::text, COALESCE(agent_run_id, ''), "
        "       COALESCE(user_email, ''), '', COALESCE(workspace_id, 1), "
        "       COALESCE(sql_text, '') || ' ' || COALESCE(user_email, '') || ' ' || "
        "       COALESCE(read_kind, '') || ' ' || COALESCE(status, '') "
        "FROM query_history ON CONFLICT DO NOTHING"
    ),
    "tool_calls": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'tool_calls', id::text, COALESCE(agent_run_id, ''), '', '', "
        "       COALESCE(workspace_id, 1), "
        "       COALESCE(tool_name, '') || ' ' || COALESCE(args_json, '') || ' ' || "
        "       COALESCE(result_summary, '') "
        "FROM agent_run_tool_calls ON CONFLICT DO NOTHING"
    ),
    "audit_log": (
        "INSERT INTO audit_search_index "
        "(axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus) "
        "SELECT 'audit_log', id::text, '', COALESCE(user_email, ''), "
        "       COALESCE(target, ''), COALESCE(workspace_id, 1), "
        "       COALESCE(action, '') || ' ' || COALESCE(target, '') || ' ' || "
        "       COALESCE(detail, '') || ' ' || COALESCE(user_email, '') "
        "FROM audit_log ON CONFLICT DO NOTHING"
    ),
}


def _pg_upsert_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the PL/pgSQL upsert function for a single source axis."""
    return f"""
CREATE OR REPLACE FUNCTION audit_search_{axis}_upsert() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO audit_search_index (
        axis, entity_id, run_id, principal, table_fqn, workspace_id, text_corpus
    ) VALUES (
        '{axis}',
        NEW.{spec["entity_col"]}::text,
        ({spec["run_id_expr"]})::text,
        ({spec["principal_expr"]})::text,
        ({spec["table_fqn_expr"]})::text,
        ({spec["workspace_id_expr"]})::int,
        ({spec["text_expr"]})::text
    )
    ON CONFLICT (axis, entity_id) DO UPDATE SET
        run_id = EXCLUDED.run_id,
        principal = EXCLUDED.principal,
        table_fqn = EXCLUDED.table_fqn,
        workspace_id = EXCLUDED.workspace_id,
        text_corpus = EXCLUDED.text_corpus;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _pg_delete_function_sql(axis: str, spec: dict[str, str]) -> str:
    """Build the PL/pgSQL delete function for a single source axis."""
    return f"""
CREATE OR REPLACE FUNCTION audit_search_{axis}_delete() RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM audit_search_index
        WHERE axis = '{axis}' AND entity_id = OLD.{spec["entity_col"]}::text;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;
"""


def _pg_attach_trigger_sql(axis: str, spec: dict[str, str]) -> list[str]:
    """Drop-and-recreate triggers on the source table for one axis."""
    table = spec["table"]
    return [
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_aiu ON {table}",
        f"DROP TRIGGER IF EXISTS audit_search_{axis}_ad ON {table}",
        (
            f"CREATE TRIGGER audit_search_{axis}_aiu "
            f"AFTER INSERT OR UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_upsert()"
        ),
        (
            f"CREATE TRIGGER audit_search_{axis}_ad "
            f"AFTER DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_search_{axis}_delete()"
        ),
    ]


def install_index(factory: sessionmaker[Session]) -> bool:
    """Provision the dialect-appropriate FTS surface idempotently.

    Used by test fixtures (which build the schema with
    :meth:`Base.metadata.create_all` and so skip the alembic
    migrations that would otherwise create the FTS layout).  The
    production code path is the alembic chain.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``True`` when the FTS surface was newly created; ``False``
        when the backend isn't supported or the surface already
        existed.
    """
    with factory() as session:
        if _is_sqlite(session):
            return _install_index_sqlite(session)
        if _is_postgres(session):
            return _install_index_postgres(session)
        return False


def _install_index_sqlite(session: Session) -> bool:
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


def _install_index_postgres(session: Session) -> bool:
    """Install (or re-attach) the PG FTS surface idempotently.

    The table + GIN index are created once per DB lifetime
    (``CREATE TABLE / INDEX IF NOT EXISTS``).  The trigger
    functions + triggers are *always* re-created because test
    fixtures drop the source tables (``Base.metadata.drop_all``)
    between tests — that drops the triggers via PG's
    drop-dependent-object cascade, but leaves
    ``audit_search_index`` alone (it isn't in ORM metadata) and
    leaves the trigger *functions* alone too.  Re-attaching the
    triggers via ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER``
    is cheap and the only correctness-preserving option.

    Args:
        session: SQLAlchemy session bound to the PG engine.

    Returns:
        ``True`` when the table was newly created (first install);
        ``False`` when only the triggers were re-attached.
    """
    table_already_existed = _is_available_postgres(session)
    if not table_already_existed:
        session.execute(text(_PG_TABLE_SQL))
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_search_text_search "
                "ON audit_search_index USING gin(text_search)"
            )
        )
        session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_audit_search_workspace "
                "ON audit_search_index (workspace_id, axis)"
            )
        )
    for axis in _PG_AXES:
        spec = _PG_TRIGGER_SPECS[axis]
        session.execute(text(_pg_upsert_function_sql(axis, spec)))
        session.execute(text(_pg_delete_function_sql(axis, spec)))
        for stmt in _pg_attach_trigger_sql(axis, spec):
            session.execute(text(stmt))
    if not table_already_existed:
        for axis in _PG_AXES:
            session.execute(text(_PG_INITIAL_POPULATE_SQL[axis]))
    session.commit()
    return not table_already_existed


def rebuild_index(factory: sessionmaker[Session]) -> dict[str, int]:
    """Drop and re-seed the FTS index from the source tables.

    Emergency-recovery hook for both backends.  Counts returned
    are post-rebuild row totals per axis.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        ``{"runs": int, "ops": int, "queries": int, "tool_calls": int,
        "audit_log": int}``.
    """
    counts: dict[str, int] = {axis: 0 for axis in VALID_AXES if axis != "all"}
    if not is_available(factory):
        return counts
    with factory() as session:
        if _is_sqlite(session):
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
        elif _is_postgres(session):
            session.execute(text("DELETE FROM audit_search_index"))
            for axis in _PG_AXES:
                session.execute(text(_PG_INITIAL_POPULATE_SQL[axis]))
            for axis_name in counts:
                count_value = (
                    session.execute(
                        text("SELECT COUNT(*) FROM audit_search_index WHERE axis = :axis"),
                        {"axis": axis_name},
                    ).scalar()
                    or 0
                )
                counts[axis_name] = int(count_value)
            session.commit()
    return counts
