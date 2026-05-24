"""AST-translation shims that map sqlglot nodes to PQL primitive args.

Each helper handles one statement family — INSERT/CTAS source SELECT
rendering, UPDATE set-clause + WHERE extraction, plain WHERE-clause
extraction for DELETE.  Plus two arithmetic utilities used by the
merge-stats reducer.
"""

from __future__ import annotations

from typing import Any

from sqlglot import expressions as exp
from sqlglot.expressions.core import Expression

from pointlessql.exceptions import SQLExecutionError
from pointlessql.pql import StmtType


def extract_source_select_sql(ast: Expression, stype: StmtType) -> str:
    """Return the source-SELECT SQL for INSERT-FROM-SELECT / CTAS.

    Args:
        ast: Parsed INSERT or CREATE TABLE AS SELECT expression.
        stype: Classification.

    Returns:
        The SELECT body rendered back to DuckDB-dialect SQL.

    Raises:
        SQLExecutionError: When the expected SELECT body is absent
            (sqlglot parse anomaly).
    """
    if stype is StmtType.INSERT_FROM_SELECT and isinstance(ast, exp.Insert):
        body = ast.expression
    elif stype is StmtType.CREATE_TABLE_AS and isinstance(ast, exp.Create):
        body = ast.expression
    else:
        body = None
    if body is None:
        raise SQLExecutionError("Could not extract source SELECT body from statement.")
    return body.sql(dialect="duckdb")


def extract_update_args(ast: Expression) -> tuple[dict[str, str], str | None]:
    """Translate UPDATE AST into ``(set_clause, where)`` strings.

    Args:
        ast: Parsed UPDATE expression.

    Returns:
        ``(set_clause, where)`` ready for :meth:`PQL.update`.

    Raises:
        SQLExecutionError: When SET assignments cannot be rendered.
    """
    if not isinstance(ast, exp.Update):  # defensive
        raise SQLExecutionError("Internal error: extract_update_args invoked on non-Update AST.")
    set_clause: dict[str, str] = {}
    for assignment in ast.args.get("expressions") or []:
        if not isinstance(assignment, exp.EQ):
            raise SQLExecutionError(
                "UPDATE SET clause must be a list of column = expression assignments.",
            )
        col = assignment.this
        rhs = assignment.expression
        if not isinstance(col, exp.Column) or rhs is None:
            raise SQLExecutionError(
                "UPDATE SET assignment must have shape `column = expression`.",
            )
        set_clause[col.name] = rhs.sql(dialect="duckdb")
    if not set_clause:
        raise SQLExecutionError("UPDATE statement has no SET assignments.")
    where_node = ast.args.get("where")
    where_sql: str | None = None
    if isinstance(where_node, exp.Where) and where_node.this is not None:
        where_sql = where_node.this.sql(dialect="duckdb")
    return set_clause, where_sql


def extract_where_sql(ast: Expression) -> str | None:
    """Return the WHERE clause's SQL string, or ``None`` for no WHERE.

    Args:
        ast: Parsed UPDATE / DELETE expression.

    Returns:
        The WHERE clause rendered as SQL, or ``None`` when absent
        (full-table DELETE / unconditional UPDATE).
    """
    where_node = ast.args.get("where") if hasattr(ast, "args") else None
    if isinstance(where_node, exp.Where) and where_node.this is not None:
        return where_node.this.sql(dialect="duckdb")
    return None


def int_or_none(value: Any) -> int | None:
    """Best-effort coerce *value* to ``int``, ``None`` on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def merge_rows_affected(stats: dict[str, Any]) -> int | None:
    """Sum the merge-stats counters into a single rows-affected number.

    Args:
        stats: Dict from :meth:`PQL.merge`.

    Returns:
        Sum of inserted+updated+deleted counts, ``None`` when the
        stats dict has none of those keys.
    """
    keys = (
        "num_target_rows_inserted",
        "num_target_rows_updated",
        "num_target_rows_deleted",
        "rows_appended",
    )
    total = 0
    seen = False
    for key in keys:
        value = int_or_none(stats.get(key))
        if value is not None:
            total += value
            seen = True
    return total if seen else None
