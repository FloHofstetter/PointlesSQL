"""Shared helpers for the SQL-editor route family.

Four module-level functions that every sub-route needs:

* :func:`short_sql_hash` — audit-log target identifier digest.
* :func:`run_sql_sync` — wraps :meth:`PQL.sql` for ``asyncio.to_thread``.
* :func:`live_queries` — per-app live DuckDB-conn registry shared by
  the execute + cancel routes.
* :func:`run_sql_export_sync` — separate execution path for the
  download route that needs the arrow buffer, not the JSON-flattened
  ``SQLResult``.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request

from pointlessql.config import Settings

_ANSI_ESCAPE_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Remove ANSI colour escapes from *text* for log-safe rendering."""
    return _ANSI_ESCAPE_RE.sub("", text)


def short_sql_hash(sql: str) -> str:
    """Return a short deterministic digest of *sql* for audit-log targets.

    The audit-log ``target`` field is a single human-readable identifier
    (``catalog:foo``, ``query:abc123``…); a full SQL string would blow
    past the reasonable column width.  A 12-char truncated SHA-256 is
    enough to correlate with the corresponding ``query_history`` row
    and to tell apart identical-looking queries.

    Args:
        sql: The SQL string to hash.

    Returns:
        A 12-character hexadecimal digest.
    """
    import hashlib

    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:12]


def run_sql_sync(
    settings: Settings,
    query: str,
    approved_tables: dict[str, str],
    max_rows: int,
    conn: Any = None,
    explain: bool = False,
    table_policies: dict[str, Any] | None = None,
    profile: bool = False,
) -> Any:
    """Execute *query* in the sync :class:`PQL` SQL bridge.

    Wrapped in a thin module-level helper so the FastAPI route can
    dispatch it via :func:`asyncio.to_thread` without capturing the
    PQL import at request time.  Any :class:`SQLExecutionError` or
    :class:`ValidationError` raised inside propagates unchanged — the
    centralised error handler turns them into RFC 9457 responses.

    Args:
        settings: Application settings (unused by :meth:`PQL.sql` at
            present but threaded through so future engine selection
            can read it without signature churn).
        query: The user-entered SQL.
        approved_tables: Full-name → storage-location map that the
            route already enforced ``SELECT`` on.
        max_rows: Row cap applied after execution.
        conn: Optional pre-created DuckDB connection so the route
            can hold the handle for cancel / timeout interrupt.
        explain: When ``True``, prepend ``EXPLAIN ANALYZE`` to the
            rewritten SQL so the caller gets the physical plan
            instead of the actual rows.
        table_policies: Optional per-table row-filter / column-mask
            policies (see :mod:`pointlessql.pql._policies`),
            collected by the enforcement hop alongside
            *approved_tables*.
        profile: When ``True``, capture DuckDB's JSON runtime profile
            alongside the regular result rows.

    Returns:
        A :class:`pointlessql.pql.pql.SQLResult` dataclass.
    """
    from pointlessql.pql import PQL

    del settings  # reserved for future engine selection
    return PQL.sql(
        query,
        approved_tables=approved_tables,
        max_rows=max_rows,
        conn=conn,
        explain=explain,
        table_policies=table_policies,
        profile=profile,
    )


def live_queries(request: Request) -> dict[str, Any]:
    """Return the per-app live-queries registry, creating it on first use.

    Stored on ``app.state._live_queries`` so every worker in the same
    process shares one dict.  Keys are client-supplied query IDs
    (UUIDs); values are live :class:`duckdb.DuckDBPyConnection`
    handles.  The execute route registers on entry and pops on exit;
    the cancel route calls ``.interrupt()`` on whatever it finds.
    Multi-worker deployments don't share this map across processes —
    cancel currently relies on single-worker correctness; multi-worker
    cancel is a future concern.

    Args:
        request: The incoming request (for ``request.app.state``).

    Returns:
        The mutable registry dict (live for the app's lifetime).
    """
    registry: dict[str, Any] | None = getattr(
        request.app.state,
        "_live_queries",
        None,
    )
    if registry is None:
        registry = {}
        request.app.state._live_queries = registry
    return registry


def run_sql_export_sync(
    settings: Settings,
    query: str,
    approved_tables: dict[str, str],
    max_rows: int,
) -> Any:
    """Execute *query* and return the full pyarrow Table.

    Export needs the arrow buffer, not a JSON-flattened dict.  We
    run via a fresh connection (no cancel registry; the export
    request is expected to be brief since it re-runs a previously
    successful query from history).  Row-cap applies so a huge
    download cannot be coerced by editing ``?format=``.

    Args:
        settings: Reserved for future engine switches.
        query: The SQL to re-run.
        approved_tables: Enforcement-gated mapping.
        max_rows: Row cap.

    Returns:
        A :class:`pyarrow.Table` already sliced to *max_rows*.

    Raises:
        SQLExecutionError: If DuckDB rejects the query at execution
            time (column not found, type mismatch, …).
    """
    import duckdb

    from pointlessql.exceptions import SQLExecutionError
    from pointlessql.pql import prepare_sql, register_delta_view

    del settings
    prepared = prepare_sql(query)
    conn = duckdb.connect()
    try:
        for ref in prepared.refs:
            register_delta_view(conn, ref, approved_tables[ref])
        try:
            arrow_table = conn.execute(prepared.rewritten_sql).to_arrow_table()
        except duckdb.Error as exc:
            raise SQLExecutionError(str(exc)) from exc
    finally:
        conn.close()
    if arrow_table.num_rows > max_rows:
        arrow_table = arrow_table.slice(0, max_rows)
    return arrow_table
