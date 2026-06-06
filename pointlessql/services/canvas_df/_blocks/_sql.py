# pyright: reportPrivateUsage=false
"""Raw-SQL blocks for the visual data-product canvas.

Compile + schema-inference helpers split out of the former single-file
block registry.  Shared infrastructure and the public dispatch live in
:mod:`pointlessql.services.canvas_df._blocks._base`; this module
registers its block types into the dispatch tables at import time.
"""

from __future__ import annotations

import re
from typing import Any

from pointlessql.services.canvas_df._blocks._base import (
    CompiledBlock,
    _bad_config,
    _coerce_str,
    _unknown_schema,
    register_block,
)
from pointlessql.services.canvas_df._types import ColumnSpec, CompileError, PinSchema

# --------------------------------------------------------------------- SQL


_SQL_PLACEHOLDER = re.compile(r"\{\{\s*in\s*\}\}")


def _compile_sql(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    query = _coerce_str(cfg.get("query")).strip()
    if not query:
        errors.append(_bad_config(node_id, "SQL.query is required (non-empty string)."))
        return None
    if "{{in}}" in query.replace(" ", "") or _SQL_PLACEHOLDER.search(query):
        src = inputs.get("in")
        if not src:
            errors.append(
                CompileError(
                    kind="missing_input",
                    node_id=node_id,
                    pin="in",
                    message="SQL block uses '{{in}}' but no upstream wired to 'in'.",
                )
            )
            return None
        rendered = _SQL_PLACEHOLDER.sub(src, query)
    else:
        rendered = query
    return CompiledBlock(sql=rendered, output_schema=output_schema)


def _infer_sql(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    query = _coerce_str(cfg.get("query")).strip()
    if not query:
        return _unknown_schema()
    inferred = _describe_sql_block(node_id, query, input_schemas, errors)
    if inferred is None:
        return _unknown_schema()
    return inferred


def _quote_ident(name: str) -> str:
    """Return *name* wrapped in DuckDB-safe double quotes."""
    return '"' + name.replace('"', '""') + '"'


def _seed_table_name(node_id: str) -> str:
    """Synthetic temp-table name standing in for the upstream input pin."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", node_id)
    return f"pql_sql_seed_{safe}"


def _describe_sql_block(
    node_id: str,
    query: str,
    input_schemas: dict[str, PinSchema],
    errors: list[CompileError],
) -> PinSchema | None:
    """Run ``DESCRIBE (rewritten_query)`` on an in-memory DuckDB conn.

    The upstream pin schema (when wired) is registered as an empty
    temp table whose columns mirror the propagated :class:`PinSchema`;
    ``{{in}}`` placeholders rewrite to that table name so DESCRIBE
    runs on a valid query without needing real data.
    """
    import duckdb

    upstream = input_schemas.get("in")
    references_in = bool(_SQL_PLACEHOLDER.search(query))
    if references_in:
        # Without a real upstream schema (no wire, or upstream itself
        # opaque) DESCRIBE cannot bind {{in}} to anything sensible —
        # fall back to unknown rather than surfacing a misleading
        # "table not found" error on the SQL node.
        if upstream is None or upstream.unknown or not upstream.columns:
            return None
    rewritten = query
    temp_table_name: str | None = None
    if upstream is not None and references_in:
        temp_table_name = _seed_table_name(node_id)
        rewritten = _SQL_PLACEHOLDER.sub(_quote_ident(temp_table_name), query)

    conn = duckdb.connect()
    try:
        if temp_table_name and upstream is not None and upstream.columns:
            col_clauses = ", ".join(
                f"{_quote_ident(col.name)} {col.duckdb_type}" for col in upstream.columns
            )
            conn.execute(
                f"CREATE TEMP TABLE {_quote_ident(temp_table_name)} ({col_clauses})"
            )
        try:
            rows = conn.execute(f"DESCRIBE ({rewritten})").fetchall()
        except (duckdb.Error, RuntimeError) as exc:
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node_id,
                    pin="out",
                    message=f"SQL.query DESCRIBE failed: {exc}",
                )
            )
            return None
    finally:
        conn.close()

    specs: list[ColumnSpec] = []
    for row in rows:
        # DuckDB DESCRIBE returns (column_name, column_type, null, key, default, extra).
        if not row:
            continue
        name = str(row[0])
        type_text = str(row[1] or "VARCHAR")
        nullable = True
        if len(row) > 2 and row[2] is not None:
            nullable = str(row[2]).upper() != "NO"
        specs.append(ColumnSpec(name=name, duckdb_type=type_text, nullable=nullable))

    if not specs:
        return None
    return PinSchema(kind="table", columns=specs, unknown=False)


register_block(
    type_name="SQL",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_sql,
    infer_fn=_infer_sql,
)