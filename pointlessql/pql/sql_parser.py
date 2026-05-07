"""Parse SQL and prepare it for the DuckDB execution path.

The SQL editor needs two things before DuckDB sees a query:
(a) the set of ``catalog.schema.table`` references so the route can
enforce ``SELECT`` per table, and (b) a rewrite that collapses each
three-part reference into a single quoted identifier matching a
pre-registered view.  DuckDB reserves ``main`` as a catalog name and
refuses to bind 3-part UC references natively, so the route
registers each Delta table at its fully-dotted quoted name (e.g.
``"main.sales.orders"``) and this module rewrites the SQL to point
at those view identifiers.

Single-statement-only scope: anything that is not a single
:class:`sqlglot.expressions.Select` (or its immediate ``WITH``
wrapper) raises :class:`SQLParseError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError
from sqlglot.expressions.core import Expression
from sqlglot.lineage import lineage as _sqlglot_lineage

from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import ValidationError
from pointlessql.table_fqn import TableFqn

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from pointlessql.services.lineage_edges import ColumnEdgeSpec


class SQLParseError(ValidationError):
    """Raised when the SQL cannot be parsed or is out-of-scope.

    Subclass of :class:`ValidationError` (was :class:`ValueError`)
    so it inherits the 422 status_code and the
    :class:`PointlessSQLError` envelope path.  The dedicated
    ``sql_parse_error`` code lets dashboards filter SQL syntax
    failures separately from generic validation errors.

    Note: ``ValidationError`` itself dual-inherits :class:`ValueError`,
    so ``except ValueError`` continues to catch :class:`SQLParseError`.

    Attributes:
        error_code: Always ``ErrorCode.SQL_PARSE_ERROR``. ``status_code``
            inherits 422 from :class:`ValidationError`.
    """

    error_code: ErrorCode = ErrorCode.SQL_PARSE_ERROR


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


def extract_column_lineage(
    *,
    sql: str,
    schema: Mapping[str, Mapping[str, Mapping[str, Mapping[str, str]]]],
    output_columns: Sequence[str],
    target_table: str = "query",
) -> list[ColumnEdgeSpec]:
    """Walk the AST of *sql* per output column and return column-edge specs.

    best-effort column-lineage extraction for
    ``pql.sql``.  Uses :func:`sqlglot.lineage.lineage` to derive the
    set of source columns each SELECT projection depends on, then
    classifies the root expression to pick a ``transform_kind``:

    * Bare column reference (with or without ``AS`` alias) →
      ``"sql_select"``.
    * Any expression that wraps the column in a function, arithmetic,
      ``CASE``, etc. → ``"sql_function"`` with ``transform_detail``
      set to the rendered subexpression.
    * sqlglot resolves to no source (window functions, lateral
      joins, ``count(*)``) → ``"sql_unknown"``.

    Args:
        sql: The single-SELECT SQL to analyse.  Must already be the
            **original** 3-part-name form — passing the rewritten
            view identifier would make sqlglot's table resolution
            useless.
        schema: Nested ``{catalog: {schema: {table: {column: type}}}}``
            mapping for the tables referenced by *sql*.  Types may
            be empty strings; sqlglot only uses the column names to
            qualify references.
        output_columns: Names of the columns the executor reported.
            Used to drive one ``lineage()`` call per column so the
            output shape matches what the agent saw at runtime.
        target_table: Synthetic target-table name to record edges
            under.  Defaults to ``"query"`` because ``pql.sql``
            results are not persisted under a UC FQN; ``op_id`` is
            the unique discriminator on ``lineage_column_map``.

    Returns:
        A list of :class:`ColumnEdgeSpec` ready to stash on the
        operation recorder.  Empty when the SQL fails to parse —
        the helper is best-effort and never raises.
    """
    from pointlessql.services.lineage_edges import ColumnEdgeSpec

    try:
        ast = sqlglot.parse_one(sql, dialect="duckdb")
    except ParseError:
        return []

    if not isinstance(ast, (exp.Select, exp.With)):
        return []

    edges: list[ColumnEdgeSpec] = []
    for col_name in output_columns:
        try:
            root = _sqlglot_lineage(col_name, ast, schema=dict(schema), dialect="duckdb")
        except Exception:  # noqa: BLE001 — sqlglot raises various errors on unresolved refs
            # bare-broad-ok: unresolved column produces sql_unknown edge
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target_table,
                    target_column=col_name,
                    transform_kind="sql_unknown",
                    transform_detail=None,
                )
            )
            continue

        downstream = getattr(root, "downstream", None) or []
        if not downstream:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target_table,
                    target_column=col_name,
                    transform_kind="sql_unknown",
                    transform_detail=None,
                )
            )
            continue
        leaves = [leaf for child in downstream for leaf in _lineage_leaves(child)]
        if not leaves:
            edges.append(
                ColumnEdgeSpec(
                    source_table=None,
                    source_column=None,
                    target_table=target_table,
                    target_column=col_name,
                    transform_kind="sql_unknown",
                    transform_detail=None,
                )
            )
            continue

        kind, detail = _classify_root_expression(root.expression)
        for leaf in leaves:
            source_table_fqn = _leaf_source_table(leaf)
            source_column_name = _leaf_source_column(leaf)
            edges.append(
                ColumnEdgeSpec(
                    source_table=source_table_fqn,
                    source_column=source_column_name,
                    target_table=target_table,
                    target_column=col_name,
                    transform_kind=kind,
                    transform_detail=detail,
                )
            )

    return edges


def _lineage_leaves(node: Any) -> Iterator[Any]:
    """Yield every leaf node (no further downstream) of an sqlglot lineage tree.

    Args:
        node: A :class:`sqlglot.lineage.Node`.

    Yields:
        Each leaf node where ``node.downstream`` is empty.
    """
    downstream = getattr(node, "downstream", None) or []
    if not downstream:
        yield node
        return
    for child in downstream:
        yield from _lineage_leaves(child)


def _leaf_source_table(leaf: Any) -> str | None:
    """Return the fully-qualified UC name of a leaf's underlying table.

    Args:
        leaf: A :class:`sqlglot.lineage.Node` whose
            :attr:`expression` should be an :class:`exp.Table`.

    Returns:
        ``"catalog.schema.table"`` when the leaf points at a fully-
        qualified table; ``None`` for unqualified leaves
        (sub-queries, derived tables, lateral joins).
    """
    expression = getattr(leaf, "expression", None)
    if not isinstance(expression, exp.Table):
        return None
    name = expression.name
    db = expression.args.get("db")
    catalog = expression.args.get("catalog")
    if catalog is None or db is None or not name:
        return None
    catalog_name = catalog.name if hasattr(catalog, "name") else str(catalog)
    db_name = db.name if hasattr(db, "name") else str(db)
    return TableFqn.from_parts(catalog_name, db_name, str(name))


def _leaf_source_column(leaf: Any) -> str | None:
    """Return the column name from a leaf-node's ``<alias>.<column>`` label.

    Args:
        leaf: A :class:`sqlglot.lineage.Node` whose ``name``
            attribute carries the qualified column reference.

    Returns:
        The column name (last dot segment of ``leaf.name``) or
        ``None`` when the label has no dot.
    """
    name = getattr(leaf, "name", "")
    if not isinstance(name, str) or "." not in name:
        return name or None
    return name.rsplit(".", 1)[-1]


def _classify_root_expression(root_expr: Any) -> tuple[str, str | None]:
    """Choose ``transform_kind`` + ``detail`` for a lineage root expression.

    Args:
        root_expr: The :attr:`Node.expression` of the lineage root —
            either an :class:`exp.Alias` wrapping the projection or
            the bare projection itself.

    Returns:
        ``(transform_kind, transform_detail)``.  Bare column refs
        (with or without ``AS``) collapse to ``("sql_select",
        None)``; everything else is ``("sql_function",
        rendered_expression)`` so the column-trace UI can show the
        formula behind a derived column.
    """
    if isinstance(root_expr, exp.Alias):
        inner = root_expr.this
    else:
        inner = root_expr

    if isinstance(inner, exp.Column):
        return "sql_select", None

    if inner is None:
        return "sql_unknown", None

    try:
        rendered = inner.sql(dialect="duckdb")
    except Exception:  # noqa: BLE001 — best-effort label
        # bare-broad-ok: rendering failure → no transform-label populated
        rendered = None
    return "sql_function", rendered


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
    """Parse *sql* as a single statement and validate the editor scope.

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
        f"Only SELECT statements are supported (got {type(root).__name__}).",
    )
