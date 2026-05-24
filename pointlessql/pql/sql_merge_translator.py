"""Translate a SQL ``MERGE`` AST into :meth:`PQL.merge` arguments.

``pql.merge`` supports two strategies — ``upsert`` (key match →
update non-key columns; otherwise insert) and ``scd2``.  SQL
``MERGE`` is more expressive: per-clause conditional updates,
``WHEN MATCHED THEN DELETE``, ``WHEN NOT MATCHED BY SOURCE``,
and ``INSERT ... BY NAME *`` are all valid AST shapes.

Rather than best-effort translating these (which would either
silently lose semantics or produce surprising behaviour), the
translator rejects anything outside the supported subset with a
structured :class:`SQLMergeUnsupportedError` that points the
user at:

* the JSON ``POST /api/pql/merge`` endpoint for ``scd2`` and
  more elaborate cases, OR
* the supported subset (``WHEN MATCHED THEN UPDATE`` +
  ``WHEN NOT MATCHED THEN INSERT``).

Supported MERGE AST shapes:

* Source: a 3-part UC table reference, OR a ``USING (SELECT …)``
  subquery (materialised through DuckDB into pandas).
* ``ON`` predicate: one or more equality comparisons of the form
  ``EQ(Column(t1.col), Column(t2.col))``, optionally combined
  with ``AND``.  Each EQ contributes one merge-key column.
* WHEN clauses: exactly one ``WHEN MATCHED THEN UPDATE``
  (with no per-clause ``AND`` condition), and optionally one
  ``WHEN NOT MATCHED THEN INSERT`` (also no condition).  Both
  must apply to all matched / unmatched rows uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import duckdb
from sqlglot import expressions as exp
from sqlglot.expressions.core import Expression

from pointlessql.pql.sql_parser import SQLParseError
from pointlessql.types import TableFqn


class SQLMergeUnsupportedError(SQLParseError):
    """Raised when a MERGE AST falls outside :meth:`PQL.merge`'s subset.

    Subclass of :class:`SQLParseError` so the centralised error
    handler maps it to a 422 with a clear ``sql_parse_error``
    code.  The ``hint`` field of the message points the user at
    the JSON ``POST /api/pql/merge`` endpoint for unsupported
    cases.
    """


@dataclass(frozen=True)
class MergeCallSpec:
    """Bundle of arguments ready for :meth:`PQL.merge`.

    Attributes:
        target: Three-part UC name of the merge target.
        source_df: Materialised source as pandas DataFrame.
        on: Non-empty list of merge-key column names.
        strategy: Always ``"upsert"`` from this translator —
            SCD-2 has no SQL syntactic counterpart and routes
            through the JSON API.
    """

    target: str
    source_df: Any
    on: list[str]
    strategy: Literal["upsert"] = "upsert"


def translate_merge_ast(
    ast: exp.Merge,
    *,
    conn: duckdb.DuckDBPyConnection,
    approved: dict[str, str],
) -> MergeCallSpec:
    """Convert a parsed MERGE AST to a :class:`MergeCallSpec`.

    Args:
        ast: The :class:`exp.Merge` node from
            :func:`pointlessql.pql.sql_parser.parse_and_classify`.
        conn: DuckDB connection used to materialise a USING
            subquery into pandas when the source is not a plain
            table reference.
        approved: ``full_name → storage_location`` map from the
            dispatcher's per-table SELECT enforcement; required
            for the source-SELECT path's view registration.

    Returns:
        A :class:`MergeCallSpec` carrying the kwargs for
        :meth:`PQL.merge`.

    Raises:
        SQLMergeUnsupportedError: When the AST contains features
            outside :meth:`PQL.merge`'s ``upsert`` subset.
        SQLParseError: When the target is not 3-part qualified.
    """  # noqa: DOC502,DOC503 — SQLParseError propagates from helpers
    target_fqn = _extract_target(ast)
    on_cols = _extract_on_columns(ast)
    if not on_cols:
        raise SQLMergeUnsupportedError(
            "MERGE ON clause must contain at least one column = column equality.",
        )
    _validate_when_clauses(ast)
    source_df = _materialise_source(ast, conn=conn, approved=approved)
    return MergeCallSpec(
        target=target_fqn,
        source_df=source_df,
        on=on_cols,
        strategy="upsert",
    )


def _extract_target(ast: exp.Merge) -> str:
    """Pull the 3-part FQN out of ``MERGE INTO catalog.schema.table [t]``.

    Args:
        ast: Parsed MERGE expression.

    Returns:
        ``"catalog.schema.table"``.

    Raises:
        SQLParseError: When the target reference is not 3-part
            qualified.
    """
    target_node = ast.args.get("this")
    if not isinstance(target_node, exp.Table):
        raise SQLParseError("MERGE target must be a table reference.")
    catalog = target_node.args.get("catalog")
    schema = target_node.args.get("db")
    name = target_node.args.get("this")
    if catalog is None or schema is None or name is None:
        raise SQLParseError(
            f"MERGE target {target_node.sql(dialect='duckdb')!r} is not "
            f"fully qualified; the editor requires catalog.schema.table.",
        )
    return TableFqn.from_parts(catalog.name, schema.name, name.name)


def _extract_on_columns(ast: exp.Merge) -> list[str]:
    """Walk the ON predicate, collect target-side merge-key names.

    Supports a single ``EQ`` node or arbitrary ``AND``-trees of
    ``EQ`` nodes.  Each EQ must compare a column from the target
    alias / table to a column from the source alias / table —
    the column-name (not the table prefix) is the merge key.

    Args:
        ast: Parsed MERGE expression.

    Returns:
        Deduplicated list of merge-key column names in source
        order.

    Raises:
        SQLMergeUnsupportedError: When the predicate contains
            anything other than ``EQ`` and ``AND`` nodes, or when
            an EQ does not compare two :class:`exp.Column` nodes.
    """
    on_node = ast.args.get("on")
    if on_node is None:
        raise SQLMergeUnsupportedError("MERGE statement is missing the ON clause.")
    columns: list[str] = []
    seen: set[str] = set()
    for eq in _flatten_and(on_node):
        if not isinstance(eq, exp.EQ):
            raise SQLMergeUnsupportedError(
                f"MERGE ON only supports `column = column` (and AND-combinations); "
                f"saw {type(eq).__name__}.",
            )
        lhs = eq.this
        rhs = eq.expression
        if not isinstance(lhs, exp.Column) or not isinstance(rhs, exp.Column):
            raise SQLMergeUnsupportedError(
                "MERGE ON equality must compare two column references.",
            )
        if lhs.name != rhs.name:
            raise SQLMergeUnsupportedError(
                f"MERGE ON column names must match across alias prefixes "
                f"(got {lhs.name!r} vs {rhs.name!r}).",
            )
        if lhs.name in seen:
            continue
        seen.add(lhs.name)
        columns.append(lhs.name)
    return columns


def _flatten_and(node: Expression) -> list[Expression]:
    """Return the leaf nodes of an ``AND`` tree, or ``[node]`` for a leaf.

    Args:
        node: Any sqlglot expression.

    Returns:
        Flat list of leaf expressions.
    """
    if isinstance(node, exp.And):
        return _flatten_and(node.this) + _flatten_and(node.expression)
    return [node]


def _validate_when_clauses(ast: exp.Merge) -> None:
    """Reject MERGE WHEN shapes outside the supported upsert subset.

    Args:
        ast: Parsed MERGE expression.

    Raises:
        SQLMergeUnsupportedError: For multiple WHEN MATCHED
            branches, conditional WHEN, WHEN MATCHED THEN DELETE,
            or WHEN NOT MATCHED BY SOURCE clauses.
    """
    whens_node = ast.args.get("whens")
    when_list = list(getattr(whens_node, "expressions", []) or [])
    if not when_list:
        raise SQLMergeUnsupportedError("MERGE statement has no WHEN clauses.")

    matched_seen = False
    not_matched_seen = False
    for when in when_list:
        if not isinstance(when, exp.When):
            raise SQLMergeUnsupportedError(
                f"MERGE WHEN entry was not an exp.When (got {type(when).__name__}).",
            )
        if when.args.get("condition") is not None:
            raise SQLMergeUnsupportedError(
                "MERGE WHEN with a per-clause AND condition is not supported. "
                "Use POST /api/pql/merge for elaborate merge scenarios.",
            )
        source_node = when.args.get("source")
        if source_node is True or source_node == "BY SOURCE":
            raise SQLMergeUnsupportedError(
                "MERGE WHEN NOT MATCHED BY SOURCE is not supported. "
                "Use POST /api/pql/merge for elaborate merge scenarios.",
            )
        then = when.args.get("then")
        is_matched = bool(when.args.get("matched"))
        if is_matched:
            if matched_seen:
                raise SQLMergeUnsupportedError(
                    "Multiple WHEN MATCHED branches are not supported.",
                )
            matched_seen = True
            if not isinstance(then, exp.Update):
                raise SQLMergeUnsupportedError(
                    "WHEN MATCHED branch must be `THEN UPDATE`. "
                    "WHEN MATCHED THEN DELETE is not supported.",
                )
        else:
            if not_matched_seen:
                raise SQLMergeUnsupportedError(
                    "Multiple WHEN NOT MATCHED branches are not supported.",
                )
            not_matched_seen = True
            if not isinstance(then, exp.Insert):
                raise SQLMergeUnsupportedError(
                    "WHEN NOT MATCHED branch must be `THEN INSERT`.",
                )

    if not matched_seen:
        raise SQLMergeUnsupportedError(
            "MERGE statement must include WHEN MATCHED THEN UPDATE.",
        )


def _materialise_source(
    ast: exp.Merge,
    *,
    conn: duckdb.DuckDBPyConnection,
    approved: dict[str, str],
) -> Any:
    """Resolve the USING clause to a pandas DataFrame.

    Two cases:

    * ``USING <full.table>`` — read the Delta table directly.
    * ``USING (SELECT …)`` — register approved Delta views in
      *conn*, run the SELECT, materialise the result.

    Args:
        ast: Parsed MERGE expression.
        conn: DuckDB connection.
        approved: ``full_name → storage_location`` map from the
            dispatcher's SELECT enforcement.

    Returns:
        A pandas DataFrame ready for :meth:`PQL.merge`.

    Raises:
        SQLMergeUnsupportedError: When the USING clause is
            neither a plain table nor a SELECT subquery.
    """
    using_node = ast.args.get("using")
    if isinstance(using_node, exp.Table):
        return _read_delta_as_pandas(using_node, approved)
    if isinstance(using_node, exp.Subquery):
        select_body = using_node.this
        if not isinstance(select_body, (exp.Select, exp.With)):
            raise SQLMergeUnsupportedError(
                "MERGE USING subquery must be a SELECT (or WITH … SELECT).",
            )
        from pointlessql.api.sql.write import (
            _materialise_select_to_pandas,  # pyright: ignore[reportPrivateUsage]
        )

        return _materialise_select_to_pandas(select_body.sql(dialect="duckdb"), approved)
    raise SQLMergeUnsupportedError(
        f"MERGE USING must be a table or a (SELECT …) subquery; "
        f"saw {type(using_node).__name__ if using_node is not None else 'None'}.",
    )


def _read_delta_as_pandas(table_node: exp.Table, approved: dict[str, str]) -> Any:
    """Read a 3-part Delta table reference into a pandas DataFrame.

    Args:
        table_node: The MERGE USING source table expression.
        approved: ``full_name → storage_location`` map.

    Returns:
        A pandas DataFrame of the table's contents.

    Raises:
        SQLMergeUnsupportedError: When the table reference is
            not 3-part qualified.
        SQLParseError: When the table is not in *approved* (the
            dispatcher should have populated it; absence here
            signals a privilege gap).
    """
    catalog = table_node.args.get("catalog")
    schema = table_node.args.get("db")
    name = table_node.args.get("this")
    if catalog is None or schema is None or name is None:
        raise SQLMergeUnsupportedError(
            f"MERGE USING table {table_node.sql(dialect='duckdb')!r} is not "
            f"fully qualified; the editor requires catalog.schema.table.",
        )
    full = TableFqn.from_parts(catalog.name, schema.name, name.name)
    location = approved.get(full)
    if not location:
        raise SQLParseError(
            f"MERGE USING source {full!r} is not approved (missing from privilege map).",
        )
    import deltalake

    return deltalake.DeltaTable(location).to_pandas()


__all__ = [
    "MergeCallSpec",
    "SQLMergeUnsupportedError",
    "translate_merge_ast",
]
