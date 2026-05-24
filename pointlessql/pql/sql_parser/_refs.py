# pyright: reportPrivateUsage=false
"""Per-statement write-target + source-ref extraction for the dispatcher."""

from __future__ import annotations

from sqlglot import expressions as exp
from sqlglot.expressions.core import Expression

from pointlessql.pql.sql_parser._types import SQLParseError, StmtType
from pointlessql.types import TableFqn


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
        "Schema reference is not fully qualified; CREATE/DROP SCHEMA requires catalog.schema.",
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
