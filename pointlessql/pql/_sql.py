"""DuckDB execution helper for :meth:`PQL.sql` (Sprint-78 split).

Phase 12 — single SELECT against DuckDB with UC-backed views. The
caller is responsible for resolving each 3-part reference to its
Delta storage location and passing the full mapping in
``approved_tables``; this module refuses to execute when a
reference is missing so a silent privilege-check bypass cannot
leak data.
"""

from __future__ import annotations

import os
import time
from typing import Any

from pointlessql.exceptions import (
    SQLExecutionError,
    ValidationError,
)
from pointlessql.pql._types import SQLResult
from pointlessql.pql.engine import register_delta_view
from pointlessql.pql.sql_parser import SQLParseError, prepare_sql
from pointlessql.services.agent_runs import operation_context


def run_sql(
    query: str,
    *,
    approved_tables: dict[str, str],
    max_rows: int = 10_000,
    conn: Any = None,
    explain: bool = False,
    agent_run_id: str | None = None,
) -> SQLResult:
    """Run a single SELECT against DuckDB with UC-backed views.

    Args:
        query: The user-entered SQL.  Must be a single SELECT.
        approved_tables: Mapping of fully-qualified table name to
            its Delta storage location.  Keys must be a superset
            of the table references extracted from *query*.
        max_rows: Post-execution row cap.  Extra rows are dropped
            and :attr:`SQLResult.truncated` is set to ``True``.
            Set by ``POINTLESSQL_SQL_MAX_ROWS`` in normal use.
        conn: Optional pre-created DuckDB connection.  When
            provided, the method uses it and leaves it open —
            the caller owns the lifecycle.  When ``None`` a
            fresh connection is created and closed here.
        explain: When ``True``, prepend ``EXPLAIN ANALYZE`` to
            the rewritten SQL so DuckDB returns the physical
            plan instead of the actual result.  The plan rows
            come back as regular columns — the caller can join
            them into a single ``<pre>`` block.  Sprint 53.
        agent_run_id: Sprint 13.8 — when set (or when the
            ``POINTLESSQL_AGENT_RUN_ID`` env var is set on a
            ``pql.sql`` call from agent-authored ``.py``) emits
            one ``agent_run_operations`` row.  The query text is
            truncated to 1024 chars in ``params_json``; the full
            text lives on the Sprint-13.9 query-history row.

    Returns:
        A :class:`SQLResult` with columns, rows, and metrics.

    Raises:
        SQLExecutionError: If *query* fails to parse, falls
            outside Phase-12's SELECT-only scope, or DuckDB
            rejects it at execution time.
        ValidationError: If a referenced table is not present in
            *approved_tables* (defence-in-depth against a route
            that forgot to enforce).
        AuditUnavailableError: If *agent_run_id* (or env var)
            resolved non-empty and the trail row cannot be
            persisted.
    """  # noqa: DOC503 — AuditUnavailableError propagates from operation_context
    import duckdb

    effective_run_id = agent_run_id or os.environ.get("POINTLESSQL_AGENT_RUN_ID")

    try:
        prepared = prepare_sql(query)
    except SQLParseError as exc:
        raise SQLExecutionError(str(exc)) from exc
    missing = [r for r in prepared.refs if r not in approved_tables]
    if missing:
        msg = (
            f"Cannot execute: table reference(s) {missing!r} were not "
            f"approved by the route layer. This is a bug in the caller."
        )
        raise ValidationError(msg)

    from pointlessql.db import get_session_factory

    factory = get_session_factory() if effective_run_id else None

    with operation_context(
        factory,
        agent_run_id=effective_run_id,
        op_name="sql",
        params={
            "query": query[:1024],
            "max_rows": max_rows,
            "explain": explain,
            "referenced_tables": list(prepared.refs),
        },
        target_table=None,
    ) as recorder:
        owns_conn = conn is None
        if owns_conn:
            conn = duckdb.connect()
        try:
            for ref in prepared.refs:
                register_delta_view(conn, ref, approved_tables[ref])

            final_sql = (
                f"EXPLAIN ANALYZE {prepared.rewritten_sql}"
                if explain
                else prepared.rewritten_sql
            )
            start = time.perf_counter()
            try:
                arrow_result = conn.execute(final_sql).to_arrow_table()
            except duckdb.Error as exc:
                raise SQLExecutionError(str(exc)) from exc
            duration_ms = int((time.perf_counter() - start) * 1000)

            total = arrow_result.num_rows
            if total > max_rows:
                arrow_result = arrow_result.slice(0, max_rows)
                truncated = True
            else:
                truncated = False

            columns = [
                {"name": name, "type": str(arrow_result.schema.field(name).type)}
                for name in arrow_result.column_names
            ]
            rows_as_dicts = arrow_result.to_pylist()
            col_names = list(arrow_result.column_names)
            rows = [[row.get(c) for c in col_names] for row in rows_as_dicts]

            if effective_run_id is not None:
                recorder.rows_affected = len(rows)

            return SQLResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                duration_ms=duration_ms,
                executed_sql=query,
                rewritten_sql=prepared.rewritten_sql,
                referenced_tables=list(prepared.refs),
            )
        finally:
            if owns_conn:
                conn.close()
