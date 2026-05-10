"""DuckDB ``EXPLAIN (FORMAT JSON)`` runner for the cost gate.

The runner mirrors the read path the SQL editor takes — fresh
in-process DuckDB connection, Delta tables registered as views at
their UC dotted name — but stops after EXPLAIN.  No row
materialisation, no result streaming, no cancellation registry.
The EXPLAIN call itself is sub-100ms even for complex plans, which
is what makes it cheap enough to gate every agent query without
touching the long-running execute path.

The route layer is responsible for:

* parsing the SQL (``prepare_sql``) so the rewritten string is
  what we actually EXPLAIN,
* enforcing UC ``SELECT`` privileges on every referenced table.

This module trusts those guarantees — bypassing them would defeat
the gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pointlessql.pql import register_delta_view
from pointlessql.services.sql.cost_estimator import CostEstimate, estimate_cost


@dataclass(frozen=True)
class ExplainResult:
    """One ``EXPLAIN (FORMAT JSON)`` invocation packaged for the route layer.

    ``plan`` is the parsed JSON tree DuckDB returned (a dict, or a
    one-element list wrapping the root — DuckDB's wrapping has
    shifted across releases).  ``cost`` is the heuristic from
    :func:`pointlessql.services.sql.cost_estimator.estimate_cost`.
    ``referenced_tables`` is the route's enforcement set, threaded
    through so the response carries it without the route having to
    construct its dict twice.
    """

    plan: Any
    cost: CostEstimate
    referenced_tables: list[str]


def run_explain(
    rewritten_sql: str,
    approved_tables: dict[str, str],
) -> ExplainResult:
    """Register Delta views, run ``EXPLAIN (FORMAT JSON)``, parse the plan.

    Opens a fresh in-process DuckDB connection, registers each
    approved table at its 3-part dotted view name, executes the
    EXPLAIN query, and closes the connection.  No timeout — EXPLAIN
    is plan-only (no scan), so it returns in milliseconds.

    The DuckDB EXPLAIN result is one row with two columns:
    ``explain_key`` (``physical_plan``) and ``explain_value`` (the
    JSON string).  We isolate the JSON string and parse it.

    Args:
        rewritten_sql: SQL string with 3-part references collapsed
            to the quoted single-identifier form (the output of
            :func:`pointlessql.pql.sql_parser.prepare_sql`).
        approved_tables: ``full_name → storage_location`` map the
            route already enforced ``SELECT`` on.  Used verbatim
            to register Delta views.

    Returns:
        ExplainResult: The parsed plan, cost estimate, and reference list.

    Raises:
        ValueError: When DuckDB returns no plan rows or the plan
            JSON is malformed.  The route layer maps these to a
            ``SQLExecutionError`` so they hit the centralised
            problem+json handler.
    """
    import duckdb

    conn = duckdb.connect()
    try:
        for full_name, storage_location in approved_tables.items():
            register_delta_view(conn, full_name, storage_location)

        cursor = conn.execute(f"EXPLAIN (FORMAT JSON) {rewritten_sql}")
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        raise ValueError("DuckDB returned no rows for EXPLAIN (FORMAT JSON).")

    plan_text: str | None = None
    for row in rows:
        for cell in row:
            if isinstance(cell, str) and cell.lstrip().startswith(("{", "[")):
                plan_text = cell
                break
        if plan_text is not None:
            break

    if plan_text is None:
        raise ValueError("DuckDB returned EXPLAIN rows but no JSON-shaped cell was found.")

    try:
        plan = json.loads(plan_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"DuckDB EXPLAIN JSON did not parse: {exc}") from exc

    cost = estimate_cost(plan)
    return ExplainResult(
        plan=plan,
        cost=cost,
        referenced_tables=list(approved_tables),
    )
