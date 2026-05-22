# pyright: reportPrivateUsage=false
"""``prepare_sql`` SELECT-side rewriter + ``extract_table_refs`` convenience shim."""

from __future__ import annotations

from sqlglot import expressions as exp
from sqlglot.expressions.core import Expression

from pointlessql.pql.sql_parser._parse import _parse_root
from pointlessql.pql.sql_parser._types import PreparedSQL, SQLParseError
from pointlessql.types import TableFqn


def prepare_sql(sql: str) -> PreparedSQL:
    """Parse, validate, and rewrite a SELECT *sql* for DuckDB execution.

    SELECT-only entry point.  Non-SELECT statements (INSERT /
    UPDATE / DELETE / MERGE / DDL) raise :class:`SQLParseError` —
    those go through :func:`parse_and_classify` and the dispatcher
    instead.

    Args:
        sql: The user-entered SQL.  Must be a single SELECT
            statement (or its immediate ``WITH`` wrapper).

    Returns:
        A :class:`PreparedSQL` carrying the extracted references
        and the rewritten SQL.

    Raises:
        SQLParseError: On parse failure, multi-statement input, non-
            SELECT top-level statement, or a non-three-part table
            reference.
    """
    root = _parse_root(sql)
    if not isinstance(root, (exp.Select, exp.With)) or (
        isinstance(root, exp.With) and not isinstance(root.this, exp.Select)
    ):
        raise SQLParseError(
            f"prepare_sql expects a SELECT statement (got {type(root).__name__}); "
            f"use parse_and_classify for non-SELECT statements.",
        )
    return _rewrite_select(root)


def _rewrite_select(root: Expression) -> PreparedSQL:
    """Walk *root*'s table refs, rewrite 3-part names to quoted views.

    Shared by :func:`prepare_sql` and (in the dispatcher) the
    source-SELECT preparation path inside ``INSERT INTO ... SELECT``
    and ``MERGE ... USING (SELECT ...)``.

    Args:
        root: A parsed :class:`exp.Select` / :class:`exp.With` node;
            mutated in place.

    Returns:
        A :class:`PreparedSQL` with the rewritten SQL string.

    Raises:
        SQLParseError: When any table reference lacks the full
            ``catalog.schema.table`` shape.
    """
    cte_aliases = {cte.alias_or_name for cte in root.find_all(exp.CTE) if cte.alias_or_name}
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
                f"fully qualified; the editor requires catalog.schema.table.",
            )
        full = TableFqn.from_parts(catalog.name, schema.name, name.name)
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
