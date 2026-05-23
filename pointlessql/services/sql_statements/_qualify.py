"""Default catalog / schema qualification for the public SQL API.

When a request body sets ``catalog`` / ``schema`` defaults, 1-part
and 2-part table references in the user SQL are rewritten to fully-
qualified 3-part form before the parser sees them.  The existing
parser refuses non-3-part refs; this module bridges that.

Implementation walks the sqlglot AST so injection-via-table-name is
impossible — identifiers go through the AST quoter, not string
concatenation.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


def qualify_sql(
    sql: str,
    *,
    default_catalog: str | None,
    default_schema: str | None,
) -> str:
    """Rewrite *sql* so every 1-/2-part table ref is fully qualified.

    * 3-part refs (``catalog.schema.table``) pass through untouched.
    * 2-part refs (``schema.table``) become ``default_catalog.schema.table``
      when ``default_catalog`` is set; otherwise pass through (the
      downstream parser will reject them with a clear error).
    * 1-part refs (``table``) become
      ``default_catalog.default_schema.table`` when both defaults
      are set; otherwise pass through.

    A SQL parse error in this stage propagates as
    :class:`sqlglot.errors.ParseError` so the caller can map it to
    DBX ``SQL_PARSE_ERROR``.

    Args:
        sql: Raw user SQL.
        default_catalog: Optional default catalog from the request.
        default_schema: Optional default schema from the request.

    Returns:
        The rewritten SQL string.  When no defaults are set and no
        refs need qualification, the result is round-tripped through
        sqlglot and may differ cosmetically (whitespace, quoting)
        from the input.

    Raises:
        ParseError: sqlglot's own ``sqlglot.errors.ParseError`` when
            *sql* cannot be parsed; callers map it to the DBX
            ``SQL_PARSE_ERROR`` envelope.
    """  # noqa: DOC502  — sqlglot raises the error inside parse_one
    if not default_catalog and not default_schema:
        return sql
    # Parse with DuckDB dialect to match the downstream engine; the
    # rewrite is dialect-agnostic but parsing with the wrong dialect
    # can misclassify identifiers.
    parsed = sqlglot.parse_one(sql, read="duckdb")
    for table in parsed.find_all(exp.Table):
        catalog = table.args.get("catalog")
        schema = table.args.get("db")
        # 3-part — leave alone.
        if catalog is not None and schema is not None:
            continue
        # 2-part (schema.table) — fill in catalog.
        if schema is not None and catalog is None and default_catalog:
            table.set("catalog", exp.to_identifier(default_catalog))
            continue
        # 1-part (table) — fill in catalog + schema together.
        if schema is None and catalog is None and default_catalog and default_schema:
            table.set("db", exp.to_identifier(default_schema))
            table.set("catalog", exp.to_identifier(default_catalog))
    return parsed.sql(dialect="duckdb")
