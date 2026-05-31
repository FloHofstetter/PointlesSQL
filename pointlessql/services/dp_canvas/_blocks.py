"""Block-type registry for the visual data-product canvas.

Each block is a tiny adapter that knows two things:

* :py:meth:`BlockSpec.compile` — turn an ``(inputs, config)`` pair
  into a DuckDB CTE body the compiler can splice into the final
  ``WITH … SELECT …`` rendering.
* :py:meth:`BlockSpec.infer_output` — given the same inputs, declare
  the downstream :class:`PinSchema` so the schema-flow validator can
  propagate types forward and surface edit-time mismatches without
  ever touching DuckDB.

Both methods are *pure* — they never read settings, never hit soyuz,
never open a database connection.  Side-effects live in the executor.

The eight initial blocks (``InputPort`` / ``Filter`` / ``Project`` /
``Join`` / ``GroupBy`` / ``Limit`` / ``SQL`` / ``OutputPort``) cover
the Lakehouse-native happy paths the user said they want first.  Each
block lives in its own ``_compile_*`` / ``_infer_*`` helper rather
than a single dispatch dict so a future block-addition wave (Phase
151) can drop in a new class without editing the registry's core.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pointlessql.services.dp_canvas._types import (
    ColumnSpec,
    CompileError,
    PinSchema,
)

_FQN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class CompiledBlock:
    """One block's compiled contribution to the SQL fragment."""

    sql: str
    output_schema: PinSchema


@dataclass(frozen=True)
class BlockSpec:
    """Static description + behaviour of one block type.

    Attributes:
        type_name: Registry key.
        input_pins: Ordered list of ``(pin_name, pin_kind)``.  v1
            only carries ``"table"`` pins, but the tuple shape leaves
            room for ``"scalar"`` / ``"model"`` later without
            re-spelling the registry.
        output_pins: Same shape; ``OutputPort`` has none.
        compile: Pure function returning a :class:`CompiledBlock` from
            ``(input_ctes, output_schema, config, errors)``.
        infer_output: Pure function returning a :class:`PinSchema`
            from ``(input_schemas, config, errors)``.  Appends to
            ``errors`` instead of raising so the editor can show every
            problem at once.
    """

    type_name: str
    input_pins: tuple[tuple[str, Literal["table"]], ...]
    output_pins: tuple[tuple[str, Literal["table"]], ...]


BLOCK_REGISTRY: dict[str, BlockSpec] = {}


def _register(spec: BlockSpec) -> BlockSpec:
    BLOCK_REGISTRY[spec.type_name] = spec
    return spec


# --------------------------------------------------------------------- helpers


def _coerce_str(value: Any, *, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str | int | float) and str(v)]
    return []


def _bad_config(node_id: str, message: str) -> CompileError:
    return CompileError(kind="bad_config", node_id=node_id, pin=None, message=message)


def _schema_columns(schema: PinSchema) -> dict[str, ColumnSpec]:
    return {col.name: col for col in schema.columns}


def _unknown_schema() -> PinSchema:
    return PinSchema(kind="table", columns=[], unknown=True)


# --------------------------------------------------------------------- InputPort


def _compile_input_port(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    del inputs  # InputPort has no upstream pins to consume
    fqn = _coerce_str(cfg.get("table_fqn"))
    if not _FQN_RE.match(fqn):
        errors.append(_bad_config(node_id, "table_fqn must be a UC three-part name"))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {fqn}",
        output_schema=output_schema,
    )


def _infer_input_port(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del input_schemas
    fqn = _coerce_str(cfg.get("table_fqn"))
    if not _FQN_RE.match(fqn):
        errors.append(_bad_config(node_id, "table_fqn must be a UC three-part name"))
        return _unknown_schema()
    if seed is not None:
        return seed
    return _unknown_schema()


_register(BlockSpec(type_name="InputPort", input_pins=(), output_pins=(("out", "table"),)))


# --------------------------------------------------------------------- Filter


def _compile_filter(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="Filter requires an upstream input on pin 'in'.",
            )
        )
        return None
    predicate = _coerce_str(cfg.get("predicate")).strip()
    if not predicate:
        errors.append(_bad_config(node_id, "Filter.predicate is required."))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {src} WHERE {predicate}",
        output_schema=output_schema,
    )


def _infer_filter(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    upstream = input_schemas.get("in")
    if upstream is None:
        return _unknown_schema()
    predicate = _coerce_str(cfg.get("predicate"))
    if predicate and not upstream.unknown:
        known_cols = _schema_columns(upstream)
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", predicate):
            if token.lower() in {"and", "or", "not", "in", "is", "null", "true", "false", "like"}:
                continue
            if token in known_cols:
                continue
        # Predicate column-reference checking is intentionally lenient — DuckDB
        # is the final arbiter for arbitrary boolean expressions.
    return upstream


_register(
    BlockSpec(type_name="Filter", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- Project


def _compile_project(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="Project requires an upstream input on pin 'in'.",
            )
        )
        return None
    columns = _coerce_str_list(cfg.get("columns"))
    if not columns:
        errors.append(_bad_config(node_id, "Project.columns is required (non-empty list)."))
        return None
    col_list = ", ".join(f'"{col}"' for col in columns)
    return CompiledBlock(
        sql=f"SELECT {col_list} FROM {src}",
        output_schema=output_schema,
    )


def _infer_project(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    upstream = input_schemas.get("in")
    columns = _coerce_str_list(cfg.get("columns"))
    if upstream is None or upstream.unknown:
        if not columns:
            return _unknown_schema()
        return PinSchema(
            kind="table",
            columns=[ColumnSpec(name=col, duckdb_type="UNKNOWN", nullable=True) for col in columns],
        )
    upstream_cols = _schema_columns(upstream)
    out_cols: list[ColumnSpec] = []
    for col in columns:
        spec = upstream_cols.get(col)
        if spec is None:
            errors.append(
                CompileError(
                    kind="type_mismatch",
                    node_id=node_id,
                    pin="in",
                    message=f"Project column {col!r} not in upstream schema.",
                )
            )
            continue
        out_cols.append(spec)
    return PinSchema(kind="table", columns=out_cols)


_register(
    BlockSpec(type_name="Project", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- Join


_JOIN_HOWS: tuple[str, ...] = ("inner", "left", "right", "full")


def _compile_join(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    left = inputs.get("left")
    right = inputs.get("right")
    if not left or not right:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="left" if not left else "right",
                message="Join requires both 'left' and 'right' inputs.",
            )
        )
        return None
    keys = _coerce_str_list(cfg.get("keys"))
    if not keys:
        errors.append(_bad_config(node_id, "Join.keys is required (non-empty list)."))
        return None
    how_raw = _coerce_str(cfg.get("how"), default="inner").lower()
    if how_raw not in _JOIN_HOWS:
        errors.append(
            _bad_config(node_id, f"Join.how must be one of {_JOIN_HOWS}; got {how_raw!r}.")
        )
        return None
    using_clause = ", ".join(f'"{key}"' for key in keys)
    join_kw = {
        "inner": "INNER",
        "left": "LEFT",
        "right": "RIGHT",
        "full": "FULL",
    }[how_raw]
    return CompiledBlock(
        sql=f"SELECT * FROM {left} {join_kw} JOIN {right} USING ({using_clause})",
        output_schema=output_schema,
    )


def _infer_join(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    left = input_schemas.get("left")
    right = input_schemas.get("right")
    if left is None or right is None:
        return _unknown_schema()
    keys = _coerce_str_list(cfg.get("keys"))
    if not keys:
        return _unknown_schema()
    left_cols = _schema_columns(left)
    right_cols = _schema_columns(right)
    if not left.unknown and not right.unknown:
        for key in keys:
            if key not in left_cols:
                errors.append(
                    CompileError(
                        kind="type_mismatch",
                        node_id=node_id,
                        pin="left",
                        message=f"Join key {key!r} not in left schema.",
                    )
                )
            if key not in right_cols:
                errors.append(
                    CompileError(
                        kind="type_mismatch",
                        node_id=node_id,
                        pin="right",
                        message=f"Join key {key!r} not in right schema.",
                    )
                )
    merged: list[ColumnSpec] = []
    seen: set[str] = set()
    # USING(...) collapses join keys to one column per key.
    for key in keys:
        spec = left_cols.get(key) or right_cols.get(key)
        if spec is not None:
            merged.append(spec)
            seen.add(spec.name)
    for spec in left.columns:
        if spec.name not in seen:
            merged.append(spec)
            seen.add(spec.name)
    for spec in right.columns:
        if spec.name not in seen:
            merged.append(spec)
            seen.add(spec.name)
    return PinSchema(kind="table", columns=merged, unknown=left.unknown or right.unknown)


_register(
    BlockSpec(
        type_name="Join",
        input_pins=(("left", "table"), ("right", "table")),
        output_pins=(("out", "table"),),
    )
)


# --------------------------------------------------------------------- GroupBy


_AGG_FNS: tuple[str, ...] = ("sum", "avg", "min", "max", "count", "count_distinct")


def _compile_group_by(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="GroupBy requires an upstream input on pin 'in'.",
            )
        )
        return None
    keys = _coerce_str_list(cfg.get("keys"))
    aggregations_raw = cfg.get("aggregations")
    if not isinstance(aggregations_raw, list) or not aggregations_raw:
        errors.append(_bad_config(node_id, "GroupBy.aggregations is required (non-empty list)."))
        return None
    select_parts: list[str] = [f'"{key}"' for key in keys]
    for idx, agg in enumerate(aggregations_raw):
        if not isinstance(agg, dict):
            errors.append(_bad_config(node_id, f"GroupBy.aggregations[{idx}] must be an object."))
            return None
        column = _coerce_str(agg.get("column"))
        fn = _coerce_str(agg.get("fn")).lower()
        alias = _coerce_str(agg.get("alias")) or f"{fn}_{column}"
        if fn not in _AGG_FNS:
            errors.append(_bad_config(node_id, f"GroupBy aggregation fn {fn!r} not in {_AGG_FNS}."))
            return None
        if not column and fn != "count":
            errors.append(
                _bad_config(node_id, f"GroupBy aggregation {alias!r}: column is required.")
            )
            return None
        if fn == "count" and not column:
            select_parts.append(f'COUNT(*) AS "{alias}"')
        elif fn == "count_distinct":
            select_parts.append(f'COUNT(DISTINCT "{column}") AS "{alias}"')
        else:
            select_parts.append(f'{fn.upper()}("{column}") AS "{alias}"')
    group_clause = ""
    if keys:
        group_clause = " GROUP BY " + ", ".join(f'"{key}"' for key in keys)
    return CompiledBlock(
        sql=f"SELECT {', '.join(select_parts)} FROM {src}{group_clause}",
        output_schema=output_schema,
    )


def _infer_group_by(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    upstream = input_schemas.get("in")
    keys = _coerce_str_list(cfg.get("keys"))
    aggregations_raw = cfg.get("aggregations") or []
    out_cols: list[ColumnSpec] = []
    upstream_cols: dict[str, ColumnSpec] = {} if upstream is None else _schema_columns(upstream)
    upstream_unknown = upstream is None or upstream.unknown
    for key in keys:
        if upstream_unknown:
            out_cols.append(ColumnSpec(name=key, duckdb_type="UNKNOWN", nullable=True))
            continue
        spec = upstream_cols.get(key)
        if spec is None:
            errors.append(
                CompileError(
                    kind="type_mismatch",
                    node_id=node_id,
                    pin="in",
                    message=f"GroupBy key {key!r} not in upstream schema.",
                )
            )
            continue
        out_cols.append(spec)
    if isinstance(aggregations_raw, list):
        for agg in aggregations_raw:
            if not isinstance(agg, dict):
                continue
            fn = _coerce_str(agg.get("fn")).lower()
            column = _coerce_str(agg.get("column"))
            alias = _coerce_str(agg.get("alias")) or f"{fn}_{column or 'star'}"
            duck_type = "DOUBLE" if fn in {"sum", "avg"} else "BIGINT"
            out_cols.append(ColumnSpec(name=alias, duckdb_type=duck_type, nullable=True))
    return PinSchema(kind="table", columns=out_cols, unknown=upstream_unknown)


_register(
    BlockSpec(type_name="GroupBy", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- Limit


def _compile_limit(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="Limit requires an upstream input on pin 'in'.",
            )
        )
        return None
    n_raw = cfg.get("n")
    if not isinstance(n_raw, int) or n_raw < 0:
        errors.append(_bad_config(node_id, "Limit.n must be a non-negative integer."))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {src} LIMIT {n_raw}",
        output_schema=output_schema,
    )


def _infer_limit(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg, node_id, errors
    return input_schemas.get("in", _unknown_schema())


_register(
    BlockSpec(type_name="Limit", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


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


_register(
    BlockSpec(type_name="SQL", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- OutputPort


OUTPUT_MODES: tuple[str, ...] = ("overwrite", "append", "merge")


def _compile_output_port(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="in",
                message="OutputPort requires an upstream input on pin 'in'.",
            )
        )
        return None
    port_name = _coerce_str(cfg.get("port_name")).strip()
    if not port_name:
        errors.append(_bad_config(node_id, "OutputPort.port_name is required."))
        return None
    target = _coerce_str(cfg.get("materialized_table"))
    if not _FQN_RE.match(target):
        errors.append(
            _bad_config(node_id, "OutputPort.materialized_table must be a UC three-part name.")
        )
        return None
    mode = _coerce_str(cfg.get("mode"), default="overwrite").lower()
    if mode not in OUTPUT_MODES:
        errors.append(_bad_config(node_id, f"OutputPort.mode must be one of {OUTPUT_MODES}."))
        return None
    if mode == "merge":
        merge_on = _coerce_str_list(cfg.get("merge_on"))
        if not merge_on:
            errors.append(
                _bad_config(node_id, "OutputPort.merge_on is required when mode='merge'.")
            )
            return None
    return CompiledBlock(
        sql=f"SELECT * FROM {src}",
        output_schema=output_schema,
    )


def _infer_output_port(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del node_id, cfg, errors, seed
    return input_schemas.get("in", _unknown_schema())


_register(BlockSpec(type_name="OutputPort", input_pins=(("in", "table"),), output_pins=()))


# --------------------------------------------------------------------- dispatch tables


_CompileFn = Callable[
    [str, dict[str, str], PinSchema, dict[str, Any], list[CompileError]],
    "CompiledBlock | None",
]
_InferFn = Callable[..., PinSchema]


_COMPILE_DISPATCH: dict[str, _CompileFn] = {
    "InputPort": _compile_input_port,
    "Filter": _compile_filter,
    "Project": _compile_project,
    "Join": _compile_join,
    "GroupBy": _compile_group_by,
    "Limit": _compile_limit,
    "SQL": _compile_sql,
    "OutputPort": _compile_output_port,
}

_INFER_DISPATCH: dict[str, _InferFn] = {
    "InputPort": _infer_input_port,
    "Filter": _infer_filter,
    "Project": _infer_project,
    "Join": _infer_join,
    "GroupBy": _infer_group_by,
    "Limit": _infer_limit,
    "SQL": _infer_sql,
    "OutputPort": _infer_output_port,
}


def compile_block(
    *,
    block_type: str,
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    """Dispatch to the per-type compile helper.

    Returns ``None`` and appends to *errors* on failure so the compiler
    keeps marching through the rest of the graph rather than aborting
    at the first issue.
    """
    handler = _COMPILE_DISPATCH.get(block_type)
    if handler is None:
        errors.append(
            CompileError(
                kind="unknown_block",
                node_id=node_id,
                pin=None,
                message=f"Unknown block_type {block_type!r}.",
            )
        )
        return None
    return handler(node_id, inputs, output_schema, cfg, errors)


def infer_block(
    *,
    block_type: str,
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    seed: PinSchema | None = None,
) -> PinSchema:
    """Dispatch to the per-type schema-inference helper."""
    handler = _INFER_DISPATCH.get(block_type)
    if handler is None:
        errors.append(
            CompileError(
                kind="unknown_block",
                node_id=node_id,
                pin=None,
                message=f"Unknown block_type {block_type!r}.",
            )
        )
        return _unknown_schema()
    return handler(node_id, input_schemas, cfg, errors, seed=seed)
