"""DuckDB execution helper for :meth:`PQL.sql`.

Runs a single SELECT against DuckDB with UC-backed views.  The
caller is responsible for resolving each 3-part reference to its
Delta storage location and passing the full mapping in
``approved_tables``; this module refuses to execute when a
reference is missing so a silent privilege-check bypass cannot
leak data.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any, cast

from pointlessql.exceptions import (
    SQLExecutionError,
    ValidationError,
)
from pointlessql.pql._types import SQLResult
from pointlessql.pql.engine import register_delta_view
from pointlessql.pql.sql_parser import (
    SQLParseError,
    extract_column_lineage,
    prepare_sql,
    project_lineage_row_id,
)
from pointlessql.services.agent_runs import operation_context
from pointlessql.types import OpName, RunId

logger = logging.getLogger(__name__)

LINEAGE_ROW_ID_COLUMN = "_lineage_row_id"


def run_sql(
    query: str,
    *,
    approved_tables: dict[str, str],
    max_rows: int = 10_000,
    conn: Any = None,
    explain: bool = False,
    agent_run_id: str | None = None,
    preserve_lineage_row_id: bool = True,
    table_policies: dict[str, Any] | None = None,
    profile: bool = False,
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
            them into a single ``<pre>`` block.
        agent_run_id: When set (or when the
            ``POINTLESSQL_AGENT_RUN_ID`` env var is set on a
            ``pql.sql`` call from agent-authored ``.py``) emits
            one ``agent_run_operations`` row.  The query text is
            truncated to 1024 chars in ``params_json``; the full
            text lives on the query-history row.  If the trail
            row cannot be persisted,
            :class:`AuditUnavailableError` propagates from
            :func:`operation_context`.
        preserve_lineage_row_id: When ``True`` (the default) and the
            call runs in an agent context, a row-preserving SELECT that
            reads a single lineage-bearing source but omits
            ``_lineage_row_id`` has the column auto-projected so the
            downstream write keeps its row-edges.  Aggregating /
            collapsing SELECTs are left untouched.  Pass ``False`` to
            opt out and return exactly the projected columns.
        table_policies: Optional mapping of fully-qualified table
            name to its effective
            :class:`pointlessql.pql._policies.TablePolicy` (or dict
            form).  Applied at view-registration time, so row
            filters and column masks hold for every query shape.
        profile: When ``True``, run the query with DuckDB JSON
            profiling enabled and attach the runtime profile tree to
            :attr:`SQLResult.profile`.  Unlike *explain*, the actual
            result rows are still returned — the profile is captured
            from the same execution.  Ignored when *explain* is set
            (the EXPLAIN ANALYZE plan already carries timings).

    Returns:
        A :class:`SQLResult` with columns, rows, and metrics.

    Raises:
        SQLExecutionError: If *query* fails to parse, falls
            outside the SELECT-only scope, or DuckDB rejects it
            at execution time.
        ValidationError: If a referenced table is not present in
            *approved_tables* (defence-in-depth against a route
            that forgot to enforce).
    """
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
        agent_run_id=cast(RunId | None, effective_run_id),
        op_name=OpName.SQL,
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
                register_delta_view(
                    conn,
                    ref,
                    approved_tables[ref],
                    policy=(table_policies or {}).get(ref),
                )

            # carry ``_lineage_row_id`` forward when a row-preserving
            # SELECT reads a lineage-bearing source but omits it, so the
            # downstream ``write_table`` / ``merge`` hook keeps its
            # row-edges instead of silently recording none.  Only in an
            # agent context (where the result is part of a tracked
            # pipeline); interactive queries are returned verbatim.
            query_sql = prepared.rewritten_sql
            lineage_sources: set[str] = set()
            schema_dict: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
            if effective_run_id is not None:
                schema_dict = _build_schema_dict(prepared.refs, conn)
                lineage_sources = set(_refs_with_lineage_row_id(prepared.refs, schema_dict))
                if preserve_lineage_row_id:
                    projected = project_lineage_row_id(
                        prepared.rewritten_sql, lineage_refs=lineage_sources
                    )
                    if projected is not None:
                        query_sql = projected
                        recorder.extra_params = {
                            **recorder.extra_params,
                            "lineage_row_id_autoprojected": True,
                        }

            if explain:
                # switch DuckDB into JSON profiling mode so
                # ``EXPLAIN ANALYZE`` returns a structured tree the
                # frontend can render with proper indentation, badges,
                # and per-operator timing.  The legacy ASCII tree is
                # preserved as a fallback by the route layer (parses
                # the JSON, formats it back to a readable text blob).
                conn.execute("PRAGMA enable_profiling='json'")

            profile_path: str | None = None
            if profile and not explain:
                # profiling-to-file keeps the result set untouched: the
                # query runs normally and DuckDB writes the JSON profile
                # tree on completion.  A tempfile (not stdout) because
                # the engine interleaves inline profiles with result
                # rendering on some duckdb versions.
                fd, profile_path = tempfile.mkstemp(prefix="pql-profile-", suffix=".json")
                os.close(fd)
                conn.execute("PRAGMA enable_profiling='json'")
                conn.execute(f"PRAGMA profiling_output='{profile_path}'")

            final_sql = f"EXPLAIN ANALYZE {query_sql}" if explain else query_sql
            start = time.perf_counter()
            try:
                arrow_result = conn.execute(final_sql).to_arrow_table()
            except duckdb.Error as exc:
                raise SQLExecutionError(str(exc)) from exc
            duration_ms = int((time.perf_counter() - start) * 1000)

            profile_tree: Any | None = None
            if profile_path is not None:
                try:
                    conn.execute("PRAGMA disable_profiling")
                except duckdb.Error:
                    logger.debug("disable_profiling raised", exc_info=True)
                profile_tree = _read_profile_file(profile_path)

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
                recorder.pending_column_edges = extract_column_lineage(
                    sql=query,
                    schema=schema_dict,
                    output_columns=col_names,
                )
                # a lineage-bearing source whose column did not survive even
                # after auto-projection is a collapsing SELECT (GROUP BY /
                # DISTINCT / aggregate / CTE / multi-source) — an intentional
                # row boundary, not the accidental 15.8 drop.  Flag it
                # explicitly so a downstream 1:1 write that declares the
                # source is never a *silent* zero-edge gap.
                if lineage_sources and LINEAGE_ROW_ID_COLUMN not in col_names:
                    logger.info(
                        "PQL.sql: query projects no %s from %s; "
                        "downstream write_table edges will be skipped",
                        LINEAGE_ROW_ID_COLUMN,
                        ", ".join(sorted(lineage_sources)),
                    )
                    recorder.extra_params = {
                        **recorder.extra_params,
                        "lineage_row_id_dropped_at_select": True,
                    }

            return SQLResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                duration_ms=duration_ms,
                executed_sql=query,
                rewritten_sql=prepared.rewritten_sql,
                referenced_tables=list(prepared.refs),
                profile=profile_tree,
            )
        finally:
            if owns_conn:
                conn.close()


def _read_profile_file(path: str) -> Any | None:
    """Read and parse the DuckDB JSON profile written to *path*.

    Best-effort by design: a missing or malformed profile must never
    fail the query that produced it — the rows are the deliverable,
    the profile is diagnostics.  The tempfile is removed either way.

    Args:
        path: Filesystem path the ``profiling_output`` PRAGMA pointed at.

    Returns:
        The parsed profile tree, or ``None`` when the file is missing,
        empty, or not valid JSON.
    """
    import json

    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            logger.debug("profile tempfile cleanup failed", exc_info=True)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _build_schema_dict(
    refs: list[str], conn: Any
) -> dict[str, dict[str, dict[str, dict[str, str]]]]:
    """Return a nested ``{catalog: {schema: {table: {column: type}}}}`` schema.

    fed to :func:`sqlglot.lineage.lineage` so it can
    qualify unqualified column references back to their owning
    table.  We use DuckDB introspection on the already-registered
    Delta views (each ref was registered by
    :func:`register_delta_view` earlier in the run) rather than
    making a soyuz round-trip — the views always exist by the time
    we get here, and the type strings are only used by sqlglot for
    type propagation that we ignore.

    Args:
        refs: Three-part UC names referenced by the query.
        conn: Live DuckDB connection with each ref registered as a
            Delta view at its dotted-name identifier.

    Returns:
        A nested dict suitable to pass as the ``schema`` kwarg of
        :func:`sqlglot.lineage.lineage`.  Empty when introspection
        fails — the caller treats this as "no lineage extractable".
    """
    schema: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    for ref in refs:
        parts = ref.split(".")
        if len(parts) != 3:
            continue
        catalog_name, schema_name, table_name = parts
        try:
            cols = conn.execute(f'DESCRIBE "{ref}"').fetchall()
        except Exception:  # noqa: BLE001 — best-effort introspection
            # bare-broad-ok: introspection skipped on DESCRIBE failure
            continue
        cat = schema.setdefault(catalog_name, {})
        sch = cat.setdefault(schema_name, {})
        tbl = sch.setdefault(table_name, {})
        for row in cols:
            col_name, col_type = (row[0], row[1]) if len(row) >= 2 else (row[0], "")
            tbl[str(col_name)] = str(col_type)
    return schema


def _refs_with_lineage_row_id(
    refs: list[str],
    schema_dict: dict[str, dict[str, dict[str, dict[str, str]]]],
) -> list[str]:
    """Return the subset of *refs* whose source schema carries ``_lineage_row_id``.

    used by :func:`run_sql` to detect SELECTs that drop
    a lineage-bearing column from the projection.  When the helper
    returns a non-empty list and ``_lineage_row_id`` is missing from
    the result columns, the agent's downstream ``write_table`` will
    silently skip row-edge emission (no ``source_row_id`` to
    correlate on).
    """
    sources: list[str] = []
    for ref in refs:
        parts = ref.split(".")
        if len(parts) != 3:
            continue
        catalog_name, schema_name, table_name = parts
        cols = schema_dict.get(catalog_name, {}).get(schema_name, {}).get(table_name, {})
        if LINEAGE_ROW_ID_COLUMN in cols:
            sources.append(ref)
    return sources
