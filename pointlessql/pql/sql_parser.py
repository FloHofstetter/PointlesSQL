"""Parse SQL and prepare it for Phase 12's DuckDB execution path.

The Phase 12 SQL editor needs two things before DuckDB sees a query:
(a) the set of ``catalog.schema.table`` references so the route can
enforce ``SELECT`` per table, and (b) a rewrite that collapses each
three-part reference into a single quoted identifier matching a
pre-registered view.  DuckDB reserves ``main`` as a catalog name and
refuses to bind 3-part UC references natively, so the route
registers each Delta table at its fully-dotted quoted name (e.g.
``"main.sales.orders"``) and this module rewrites the SQL to point
at those view identifiers.

Sprint 49 single-statement-only scope: anything that is not a
single :class:`sqlglot.expressions.Select` (or its immediate
``WITH`` wrapper) raises :class:`SQLParseError`.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError
from sqlglot.expressions.core import Expression


class SQLParseError(ValueError):
    """Raised when the SQL cannot be parsed or is out-of-scope for Phase 12.

    Distinguished from :class:`pointlessql.exceptions.ValidationError`
    so the route handler can map it specifically to HTTP 400 without
    scanning the message text.
    """


@dataclass(frozen=True)
class PreparedSQL:
    """A parsed SQL statement ready to hand to DuckDB.

    Attributes:
        refs: The distinct 3-part table names the query references,
            in first-appearance order.
        rewritten_sql: The SQL string with every 3-part reference
            collapsed to a single quoted identifier.  Safe to execute
            against a DuckDB connection that has each ref registered
            as a view at the identical dotted identifier.
    """

    refs: list[str]
    rewritten_sql: str


def prepare_sql(sql: str) -> PreparedSQL:
    """Parse, validate, and rewrite *sql* for DuckDB-side execution.

    Args:
        sql: The user-entered SQL.  Must be a single statement.

    Returns:
        A :class:`PreparedSQL` carrying the extracted references
        and the rewritten SQL.

    Raises:
        SQLParseError: On parse failure, multi-statement input, non-
            SELECT top-level statement, or a non-three-part table
            reference.
    """
    root = _parse_root(sql)
    cte_aliases = {
        cte.alias_or_name
        for cte in root.find_all(exp.CTE)
        if cte.alias_or_name
    }
    refs: list[str] = []
    seen: set[str] = set()
    for table in root.find_all(exp.Table):
        if table.name in cte_aliases and not table.args.get("db"):
            continue
        catalog = table.args.get("catalog")
        schema = table.args.get("db")
        name = table.args.get("this")
        if catalog is None or schema is None or name is None:
            raise SQLParseError(
                f"Table reference {table.sql(dialect='duckdb')!r} is not "
                f"fully qualified; Phase 12 requires catalog.schema.table.",
            )
        full = f"{catalog.name}.{schema.name}.{name.name}"
        alias = table.args.get("alias")
        replacement = exp.Table(
            this=exp.Identifier(this=full, quoted=True),
            alias=alias,
        )
        table.replace(replacement)
        if full in seen:
            continue
        seen.add(full)
        refs.append(full)
    return PreparedSQL(refs=refs, rewritten_sql=root.sql(dialect="duckdb"))


def extract_table_refs(sql: str) -> list[str]:
    """Return the distinct 3-part table references used by *sql*.

    Convenience shim around :func:`prepare_sql` for callers that only
    need the reference list (e.g. :func:`services.query_history.record_query`
    parsing a historical SQL string).

    Args:
        sql: The SQL string to inspect.

    Returns:
        A list of fully-qualified ``"catalog.schema.table"`` strings
        in the order they first appear in the parse tree.

    Raises:
        SQLParseError: Same conditions as :func:`prepare_sql`.
    """  # noqa: DOC502 — propagates from prepare_sql
    return prepare_sql(sql).refs


def _parse_root(sql: str) -> Expression:
    """Parse *sql* as a single statement and validate Phase-49 scope.

    sqlglot's :func:`sqlglot.parse` returns ``list[Expr | None]``;
    every real AST node is an :class:`exp.Expression` subclass at
    runtime, so we narrow via explicit :class:`exp.Select` /
    :class:`exp.With` checks.  A ``With`` is accepted only when it
    wraps a single ``Select``.

    Args:
        sql: The raw SQL string.

    Returns:
        The top-level sqlglot expression.

    Raises:
        SQLParseError: On empty input, parse failure, multi-statement
            input, or non-SELECT top-level statement.
    """
    sql = (sql or "").strip()
    if not sql:
        raise SQLParseError("Empty SQL.")

    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError as exc:
        raise SQLParseError(f"Could not parse SQL: {exc}") from exc

    statements = [s for s in parsed if s is not None]
    if len(statements) != 1:
        raise SQLParseError(
            f"Exactly one SQL statement is required (got {len(statements)}).",
        )
    root = statements[0]

    if isinstance(root, exp.Select):
        return root
    if isinstance(root, exp.With) and isinstance(root.this, exp.Select):
        return root
    raise SQLParseError(
        f"Only SELECT statements are supported in Phase 12 "
        f"(got {type(root).__name__}).",
    )
