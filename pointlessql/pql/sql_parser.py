"""Parse SQL and prepare it for the right execution path.

The SQL editor classifies each statement and dispatches to one of
three families:

* **SELECT (and ``WITH ... SELECT``)** runs through DuckDB.  The
  route extracts the 3-part UC table references, enforces ``SELECT``
  per table, and rewrites each reference to a quoted identifier
  matching a pre-registered Delta view.  DuckDB reserves ``main``
  as a catalog name and refuses to bind 3-part UC references
  natively, hence the rewrite.
* **DML (``INSERT INTO ... SELECT``, ``UPDATE``, ``DELETE``,
  ``MERGE``, ``CREATE TABLE ... AS SELECT``)** routes through the
  PQL primitives (``write_table`` / ``update`` / ``delete`` /
  ``merge``).  Source SELECT subqueries still go through the
  DuckDB rewriter for materialisation; the target table stays as
  a plain FQN because Delta writes bypass DuckDB.
* **DDL (``CREATE/DROP SCHEMA``, ``DROP TABLE``, ``ALTER TABLE``)**
  routes through the soyuz client.

Multi-statement input is still rejected — :func:`_parse_root`
enforces "exactly one statement".  Use :func:`parse_batch`
(Phase 63.6) for the batch path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
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


class StmtType(StrEnum):
    """Classification of the top-level SQL statement.

    Drives dispatcher routing in
    :mod:`pointlessql.api.sql_dispatcher`.  Each value names the
    primitive family the dispatcher will route to (DuckDB rewriter,
    PQL primitive, or soyuz facade).
    """

    SELECT = "select"
    INSERT_FROM_SELECT = "insert_from_select"
    CREATE_TABLE_AS = "create_table_as"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    DROP_TABLE = "drop_table"
    CREATE_SCHEMA = "create_schema"
    DROP_SCHEMA = "drop_schema"
    ALTER_TABLE = "alter_table"


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


def parse_and_classify(sql: str) -> tuple[Expression, StmtType]:
    """Parse *sql* and return its AST plus dispatcher classification.

    Single entry point for the SQL editor's dispatcher path.
    Accepts every statement type the dispatcher can handle —
    SELECT / WITH, INSERT, UPDATE, DELETE, MERGE, CREATE TABLE
    (with or without AS SELECT), DROP TABLE, CREATE SCHEMA,
    DROP SCHEMA, and ALTER TABLE.  Anything else (CREATE/DROP
    CATALOG, generic ``Command`` fall-throughs, multi-statement
    input) raises :class:`SQLParseError`.

    Args:
        sql: The user-entered SQL.  Must be exactly one statement.

    Returns:
        ``(ast, stype)`` — the sqlglot expression and its
        :class:`StmtType` classification.

    Raises:
        SQLParseError: On parse failure, multi-statement input, or
            an unsupported statement class.
    """  # noqa: DOC502 — propagates from _parse_root + classify
    root = _parse_root(sql)
    return root, classify(root)


def classify(ast: Expression) -> StmtType:
    """Map a parsed top-level AST node to a :class:`StmtType`.

    Order of checks matters: ``CREATE TABLE ... AS SELECT`` must be
    distinguished from bare ``CREATE TABLE`` via the presence of
    ``ast.expression``; ``Drop`` / ``Create`` use the ``kind``
    string ('TABLE', 'SCHEMA') to discriminate object families.

    Args:
        ast: The top-level expression from :func:`_parse_root`.

    Returns:
        The matching :class:`StmtType`.

    Raises:
        SQLParseError: When the AST does not match any supported
            statement family.  CREATE/DROP CATALOG land here
            (sqlglot parses them as :class:`exp.Command` with no
            structured args) — use the admin UI for catalog
            management.
    """
    if isinstance(ast, (exp.Select, exp.With)):
        return StmtType.SELECT
    if isinstance(ast, exp.Insert):
        return StmtType.INSERT_FROM_SELECT
    if isinstance(ast, exp.Update):
        return StmtType.UPDATE
    if isinstance(ast, exp.Delete):
        return StmtType.DELETE
    if isinstance(ast, exp.Merge):
        return StmtType.MERGE
    if isinstance(ast, exp.Create):
        kind = (ast.args.get("kind") or "").upper()
        if kind == "TABLE":
            if ast.expression is None:
                raise SQLParseError(
                    "Bare CREATE TABLE (without AS SELECT) is not supported "
                    "from the SQL editor; use the table-detail UI's New Table form.",
                )
            return StmtType.CREATE_TABLE_AS
        if kind == "SCHEMA":
            return StmtType.CREATE_SCHEMA
        raise SQLParseError(
            f"CREATE {kind} is not supported from the SQL editor; "
            f"use the corresponding admin UI surface.",
        )
    if isinstance(ast, exp.Drop):
        kind = (ast.args.get("kind") or "").upper()
        if kind == "TABLE":
            return StmtType.DROP_TABLE
        if kind == "SCHEMA":
            return StmtType.DROP_SCHEMA
        raise SQLParseError(
            f"DROP {kind} is not supported from the SQL editor; "
            f"use the corresponding admin UI surface.",
        )
    if isinstance(ast, exp.Alter):
        kind = (ast.args.get("kind") or "").upper()
        if kind == "TABLE":
            return StmtType.ALTER_TABLE
        raise SQLParseError(
            f"ALTER {kind} is not supported from the SQL editor.",
        )
    raise SQLParseError(
        f"Unsupported statement type: {type(ast).__name__}.",
    )


def extract_write_target(ast: Expression, stype: StmtType) -> str:
    """Return the 3-part FQN of the write target for a non-SELECT *ast*.

    The dispatcher uses this to scope the per-statement ``MODIFY``
    privilege check before invoking the PQL primitive or soyuz
    facade.  For DML the target is always the first
    :class:`exp.Table` directly under the statement root (not any
    nested SELECT source).

    Args:
        ast: A parsed non-SELECT expression.
        stype: The classification from :func:`classify`.

    Returns:
        The fully-qualified ``"catalog.schema.table"`` (or
        ``"catalog.schema"`` for schema-level DDL).

    Raises:
        SQLParseError: When the target is not three-part qualified
            or when called for a stype with no extractable target
            (currently only :attr:`StmtType.SELECT`).
    """
    if stype is StmtType.SELECT:
        raise SQLParseError("SELECT has no write target.")
    target_node: exp.Table | None
    if stype is StmtType.CREATE_SCHEMA or stype is StmtType.DROP_SCHEMA:
        return _extract_schema_target(ast)
    if isinstance(ast, exp.Insert):
        target_node = ast.this if isinstance(ast.this, exp.Table) else None
    elif isinstance(ast, (exp.Update, exp.Delete)):
        target_node = ast.this if isinstance(ast.this, exp.Table) else None
    elif isinstance(ast, exp.Merge):
        node = ast.args.get("this")
        target_node = node if isinstance(node, exp.Table) else None
    elif isinstance(ast, exp.Create):
        # CREATE TABLE ... AS SELECT — `this` is a Schema wrapping a Table.
        node = ast.this
        if isinstance(node, exp.Schema):
            inner = node.this
            target_node = inner if isinstance(inner, exp.Table) else None
        elif isinstance(node, exp.Table):
            target_node = node
        else:
            target_node = None
    elif isinstance(ast, exp.Drop):
        node = ast.this
        target_node = node if isinstance(node, exp.Table) else None
    elif isinstance(ast, exp.Alter):
        node = ast.this
        target_node = node if isinstance(node, exp.Table) else None
    else:
        target_node = None
    if target_node is None:
        raise SQLParseError(
            f"Could not extract write target from {type(ast).__name__}.",
        )
    catalog = target_node.args.get("catalog")
    schema = target_node.args.get("db")
    name = target_node.args.get("this")
    if catalog is None or schema is None or name is None:
        raise SQLParseError(
            f"Write target {target_node.sql(dialect='duckdb')!r} is not "
            f"fully qualified; the editor requires catalog.schema.table.",
        )
    return TableFqn.from_parts(catalog.name, schema.name, name.name)


def _extract_schema_target(ast: Expression) -> str:
    """Return ``"catalog.schema"`` for a CREATE/DROP SCHEMA statement.

    sqlglot parses ``CREATE SCHEMA main.bronze`` as
    ``exp.Create(this=Table(catalog=main, db=bronze, this=None))``
    — the *catalog* is in :attr:`Table.args["catalog"]` and the
    *schema name* is in :attr:`Table.args["db"]`.  Two-part
    qualification is mandatory because schemas without a parent
    catalog are ambiguous in UC.

    Args:
        ast: An :class:`exp.Create` or :class:`exp.Drop` whose
            ``kind`` is ``"SCHEMA"``.

    Returns:
        ``"catalog.schema"``.

    Raises:
        SQLParseError: When the schema reference is not two-part
            qualified.
    """
    node = ast.this
    if isinstance(node, exp.Schema):
        node = node.this
    if isinstance(node, exp.Table):
        catalog = node.args.get("catalog")
        schema = node.args.get("db")
        if catalog is not None and schema is not None:
            return f"{catalog.name}.{schema.name}"
    raise SQLParseError(
        "Schema reference is not fully qualified; "
        "CREATE/DROP SCHEMA requires catalog.schema.",
    )


def extract_source_refs(ast: Expression, stype: StmtType) -> list[str]:
    """Return the distinct source table refs of a write statement.

    Source refs are the tables a write reads FROM (the SELECT
    subqueries inside INSERT, MERGE, UPDATE/DELETE-with-correlated-
    subquery; the source table of MERGE's USING clause).  For
    UPDATE / DELETE without subqueries the list is empty (the
    target appears in the AST but is not a source).

    Args:
        ast: A parsed non-SELECT expression.
        stype: The classification from :func:`classify`.

    Returns:
        A list of fully-qualified ``"catalog.schema.table"`` strings
        in first-appearance order (deduplicated, target excluded).
    """
    if stype is StmtType.SELECT:
        return []
    try:
        target_fqn = extract_write_target(ast, stype)
    except SQLParseError:
        target_fqn = ""
    refs: list[str] = []
    seen: set[str] = set()
    cte_aliases = {cte.alias_or_name for cte in ast.find_all(exp.CTE) if cte.alias_or_name}
    for table in ast.find_all(exp.Table):
        if table.name in cte_aliases and not table.args.get("db"):
            continue
        catalog = table.args.get("catalog")
        schema = table.args.get("db")
        name = table.args.get("this")
        if catalog is None or schema is None or name is None:
            continue
        full = TableFqn.from_parts(catalog.name, schema.name, name.name)
        if full == target_fqn:
            continue
        if full in seen:
            continue
        seen.add(full)
        refs.append(full)
    return refs


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
    """Parse *sql* as a single statement and return its AST root.

    sqlglot's :func:`sqlglot.parse` returns ``list[Expr | None]``;
    every real AST node is an :class:`exp.Expression` subclass at
    runtime.  Statement-class validation is the caller's job —
    :func:`prepare_sql` raises if the root is not a SELECT;
    :func:`classify` accepts the broader set the dispatcher
    handles.

    Args:
        sql: The raw SQL string.

    Returns:
        The top-level sqlglot expression.

    Raises:
        SQLParseError: On empty input, parse failure, or
            multi-statement input.
    """
    sql = (sql or "").strip()
    if not sql:
        raise SQLParseError("Empty SQL.")

    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError as exc:
        raise SQLParseError(f"Could not parse SQL: {exc}") from exc

    statements: list[Expression] = [s for s in parsed if isinstance(s, Expression)]
    if len(statements) != 1:
        raise SQLParseError(
            f"Exactly one SQL statement is required (got {len(statements)}).",
        )
    return statements[0]


def parse_batch(sql: str) -> list[Expression]:
    """Parse *sql* as one or more statements and return their ASTs.

    Used by the multi-statement editor path (Phase 63.6).  Empty
    input still raises; otherwise returns one AST per
    semicolon-separated statement, in source order.

    Args:
        sql: One or more SQL statements separated by ``;``.

    Returns:
        A list of top-level sqlglot expressions, length >= 1.

    Raises:
        SQLParseError: On empty input or parse failure.
    """
    sql = (sql or "").strip()
    if not sql:
        raise SQLParseError("Empty SQL.")
    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError as exc:
        raise SQLParseError(f"Could not parse SQL: {exc}") from exc
    statements: list[Expression] = [s for s in parsed if isinstance(s, Expression)]
    if not statements:
        raise SQLParseError("No SQL statements found.")
    return statements
