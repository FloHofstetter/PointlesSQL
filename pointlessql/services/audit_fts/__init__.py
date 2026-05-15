"""Free-text search across the audit lake (per-dialect split).

The audit cockpit's ``GET /api/audit/search`` is dialect-portable:
a SQLite FTS5 virtual table on SQLite, a Postgres ``tsvector +
GIN`` index on Postgres, both hidden behind the same :func:`search`
entry point so the route layer doesn't have to care about backend
specifics.

Layout summary:

* :mod:`._sqlite` — alembic ``y5u7v9w1x3z5`` creates a single
  ``audit_search`` virtual table with five trigger-maintained axes
  (``runs``, ``ops``, ``queries``, ``tool_calls``, ``audit_log``).
  All SQLite-side DDL + SQL generation lives here.
* :mod:`._postgres` — alembic ``hh8j0l2n4p6r`` creates an
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


_FTS_RESERVED = re.compile(r"[^\w._\-\s]", re.UNICODE)


def _sanitise_query(query: str) -> str:
    """Strip FTS-reserved punctuation from a user-supplied query.

    Both backends use the same sanitiser so cross-dialect behaviour
    matches.  The default tokenizer treats ``.``/``_``/``-`` as
    safe (UC FQNs survive); everything else that could confuse the
    FTS5 parser or PG ``plainto_tsquery`` is space-replaced.
    """
    return _FTS_RESERVED.sub(" ", query).strip()


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
    from pointlessql.services.audit_fts import _postgres, _sqlite

    with factory() as session:
        if _is_sqlite(session):
            return _sqlite.is_available(session)
        if _is_postgres(session):
            return _postgres.is_available(session)
        return False


def search(
    factory: sessionmaker[Session],
    *,
    query: str,
    axis: Axis = "all",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    workspace_id: int | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Search the audit lake; returns a JSON-shaped result dict.

    Args:
        factory: SQLAlchemy session factory.
        query: Free-text query.  Sanitised before forwarding.
        axis: Restrict to a single axis or ``all``.
        since: Optional ISO-aware lower bound on the source row's
            primary timestamp.
        until: Optional upper bound (exclusive).
        limit: Max rows returned per page (``rank``-ordered, most
            relevant first).
        offset: Zero-based offset for paged calls.  Both SQLite and
            Postgres dialects honor this.
        workspace_id: Restrict to a single workspace's audit corpus.
            ``None`` skips the filter (super-admin cross-workspace
            lens).
        kind: Restrict to one polymorphic entity kind (``'dp'``,
            ``'table'``, ``'model'``, …).  Only populated for the
            ``audit_log`` axis; non-audit axes match no rows when
            the filter is set.  ``None`` keeps the filter off.

    Returns:
        ``{"available", "query", "axis", "since", "until", "limit",
        "offset", "next_offset", "workspace_id", "kind", "results",
        "total_count"}``.  ``next_offset`` is ``offset + limit`` when
        the page came back full and ``None`` once the page is the
        tail of the result set.

    Raises:
        ValueError: ``axis`` outside :data:`VALID_AXES`.
    """
    from pointlessql.services.audit_fts import _postgres, _sqlite

    if axis not in VALID_AXES:
        raise ValueError(f"unknown axis: {axis!r}")

    safe_offset = max(offset, 0)
    response: dict[str, Any] = {
        "available": False,
        "query": query,
        "axis": axis,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "limit": limit,
        "offset": safe_offset,
        "next_offset": None,
        "workspace_id": workspace_id,
        "kind": kind,
        "results": [],
        "total_count": 0,
    }
    sanitised = _sanitise_query(query)
    if not sanitised:
        return response

    with factory() as session:
        if _is_sqlite(session):
            results = _sqlite.search(
                session,
                sanitised=sanitised,
                axis=axis,
                limit=limit,
                offset=safe_offset,
                workspace_id=workspace_id,
                kind=kind,
            )
        elif _is_postgres(session):
            results = _postgres.search(
                session,
                sanitised=sanitised,
                axis=axis,
                limit=limit,
                offset=safe_offset,
                workspace_id=workspace_id,
                kind=kind,
            )
        else:
            return response

        if results is None:
            return response

        if since is not None or until is not None:
            results = _apply_time_filter(session, results, since=since, until=until)

        # Page-tail detection: a full page of ``limit`` rows from the
        # underlying SQL implies more candidates may exist.  Time
        # filters happen post-SQL so a partial page here is genuinely
        # exhausted at this offset under these filters.
        next_offset = safe_offset + limit if len(results) >= limit else None
        response.update(
            {
                "available": True,
                "results": results,
                "total_count": len(results),
                "next_offset": next_offset,
            }
        )
    return response


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
    from pointlessql.services.audit_fts import _postgres, _sqlite

    with factory() as session:
        if _is_sqlite(session):
            return _sqlite.install_index(session)
        if _is_postgres(session):
            return _postgres.install_index(session)
        return False


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
    from pointlessql.services.audit_fts import _postgres, _sqlite

    counts: dict[str, int] = {axis: 0 for axis in VALID_AXES if axis != "all"}
    if not is_available(factory):
        return counts
    with factory() as session:
        if _is_sqlite(session):
            return _sqlite.rebuild_index(session, counts)
        if _is_postgres(session):
            return _postgres.rebuild_index(session, counts)
    return counts


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


__all__ = [
    "Axis",
    "VALID_AXES",
    "is_available",
    "install_index",
    "logger",
    "rebuild_index",
    "search",
]
