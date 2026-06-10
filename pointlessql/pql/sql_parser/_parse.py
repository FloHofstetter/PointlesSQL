"""Raw sqlglot wrappers — single-statement parse, batch parse, classify."""

from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError
from sqlglot.expressions.core import Expression

from pointlessql.pql.sql_parser._types import SQLParseError, StmtType


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

    Used by the multi-statement editor path.  Empty
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


def parse_and_classify(sql: str) -> tuple[Expression, StmtType]:
    """Parse *sql* and return its AST plus dispatcher classification.

    Single entry point for the SQL editor's dispatcher path.
    Accepts every statement type the dispatcher can handle —
    SELECT / WITH, INSERT, UPDATE, DELETE, MERGE, CREATE TABLE
    (with or without AS SELECT), DROP TABLE, CREATE SCHEMA,
    DROP SCHEMA, and ALTER TABLE.  Anything else (CREATE/DROP
    CATALOG, generic ``Command`` fall-throughs, multi-statement
    input) propagates :class:`SQLParseError` from
    :func:`_parse_root` / :func:`classify`, as do plain parse
    failures.

    Args:
        sql: The user-entered SQL.  Must be exactly one statement.

    Returns:
        ``(ast, stype)`` — the sqlglot expression and its
        :class:`StmtType` classification.
    """
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
