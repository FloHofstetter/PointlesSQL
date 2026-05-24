# pyright: reportPrivateUsage=false
"""``inject_limit`` — append a default LIMIT to a SELECT when missing.

Used by the Lens read-only Q&A surface to cap any
SELECT the agent issues.  Idempotent on already-limited SQL.
"""

from __future__ import annotations

from sqlglot import expressions as exp

from pointlessql.pql.sql_parser._parse import _parse_root
from pointlessql.pql.sql_parser._types import SQLParseError


def inject_limit(sql: str, default_limit: int = 1000) -> str:
    """Inject a top-level ``LIMIT`` clause if *sql* doesn't carry one.

    Used by the Lens read-only Q&A surface to cap any
    SELECT the agent issues.  Idempotent: a SELECT that already has a
    ``LIMIT`` clause (user / agent override) is returned unchanged.
    Nested SELECTs inside ``WITH`` / subquery / CTE definitions are
    not touched — only the outermost result-shaping LIMIT.

    Non-SELECT statements (DDL / DML) raise :class:`SQLParseError`
    so callers can be sure the resulting SQL is read-only.

    Args:
        sql: The SQL string to gate.  Must be a single SELECT
            (or its immediate ``WITH`` wrapper).
        default_limit: The LIMIT value to inject when the input has
            none.  Must be positive; non-positive values are clamped
            to 1.

    Returns:
        The original SQL with a top-level ``LIMIT N`` appended when
        absent; the original SQL verbatim when a LIMIT is already
        present.

    Raises:
        SQLParseError: When *sql* is not a SELECT (or
            ``WITH ... SELECT``) statement, or when parsing fails.
    """
    capped = max(1, int(default_limit))
    root = _parse_root(sql)
    select_node: exp.Select | None = None
    if isinstance(root, exp.Select):
        select_node = root
    elif isinstance(root, exp.With) and isinstance(root.this, exp.Select):
        select_node = root.this
    if select_node is None:
        raise SQLParseError(
            f"inject_limit expects a SELECT statement (got "
            f"{type(root).__name__})."
        )
    if select_node.args.get("limit") is not None:
        return sql
    select_node.set("limit", exp.Limit(expression=exp.Literal.number(capped)))
    return root.sql(dialect="duckdb")
