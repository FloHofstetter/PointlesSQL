# pyright: reportPrivateUsage=false
"""Reshape blocks for the visual data-product canvas.

Compile + schema-inference helpers split out of the former single-file
block registry.  Shared infrastructure and the public dispatch live in
:mod:`pointlessql.services.canvas_df._blocks._base`; this module
registers its block types into the dispatch tables at import time.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.canvas_df._blocks._base import (
    CompiledBlock,
    _bad_config,
    _coerce_str,
    _coerce_str_list,
    _unknown_schema,
    register_block,
)
from pointlessql.services.canvas_df._types import ColumnSpec, CompileError, PinSchema

# --------------------------------------------------------------------- Window


_WINDOW_FNS: tuple[str, ...] = (
    "row_number",
    "rank",
    "dense_rank",
    "lag",
    "lead",
    "sum",
    "avg",
    "min",
    "max",
    "count",
)


def _compile_window(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Window requires an upstream input on pin 'in'."))
        return None
    fn = _coerce_str(cfg.get("function")).lower().strip()
    if fn not in _WINDOW_FNS:
        errors.append(_bad_config(node_id, f"Window.function must be one of {_WINDOW_FNS}."))
        return None
    alias = _coerce_str(cfg.get("target_alias")).strip()
    if not alias:
        errors.append(_bad_config(node_id, "Window.target_alias is required."))
        return None
    args = _coerce_str_list(cfg.get("args"))
    partition = _coerce_str_list(cfg.get("partition_by"))
    order = _coerce_str_list(cfg.get("order_by"))
    args_sql = ", ".join(f'"{a}"' for a in args) if args else "*" if fn == "count" else ""
    partition_sql = f"PARTITION BY {', '.join(f'"{c}"' for c in partition)} " if partition else ""
    order_sql = f"ORDER BY {', '.join(f'"{c}"' for c in order)} " if order else ""
    over = f"({partition_sql}{order_sql}".rstrip() + ")"
    return CompiledBlock(
        sql=f'SELECT *, {fn.upper()}({args_sql}) OVER {over} AS "{alias}" FROM {src}',
        output_schema=output_schema,
    )


def _infer_window(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id
    upstream = input_schemas.get("in")
    alias = _coerce_str(cfg.get("target_alias")).strip()
    fn = _coerce_str(cfg.get("function")).lower().strip()
    if upstream is None or upstream.unknown:
        return _unknown_schema()
    alias_type = "BIGINT" if fn in {"row_number", "rank", "dense_rank", "count"} else "DOUBLE"
    new_col = ColumnSpec(name=alias or "window_value", duckdb_type=alias_type, nullable=True)
    return PinSchema(kind="table", columns=[*upstream.columns, new_col])


register_block(
    type_name="Window",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_window,
    infer_fn=_infer_window,
)


# --------------------------------------------------------------------- Pivot


def _compile_pivot(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Pivot requires an upstream input."))
        return None
    on_col = _coerce_str(cfg.get("on_column")).strip()
    value_col = _coerce_str(cfg.get("value_column")).strip()
    agg = _coerce_str(cfg.get("aggregate"), default="sum").lower().strip()
    if not on_col or not value_col:
        errors.append(_bad_config(node_id, "Pivot.on_column and Pivot.value_column are required."))
        return None
    if agg not in {"sum", "avg", "min", "max", "count", "count_distinct"}:
        errors.append(_bad_config(node_id, f"Pivot.aggregate {agg!r} not supported."))
        return None
    agg_sql = "COUNT(DISTINCT" if agg == "count_distinct" else agg.upper() + "("
    suffix = ")"
    return CompiledBlock(
        sql=(f'PIVOT {src} ON "{on_col}" USING {agg_sql}"{value_col}"{suffix}'),
        output_schema=output_schema,
    )


def _infer_pivot(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id, cfg, input_schemas
    # Pivot produces a dynamic column set — schema-flow downstream sees unknown.
    return _unknown_schema()


register_block(
    type_name="Pivot",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_pivot,
    infer_fn=_infer_pivot,
)


# --------------------------------------------------------------------- Unpivot


def _compile_unpivot(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Unpivot requires an upstream input."))
        return None
    value_cols = _coerce_str_list(cfg.get("value_columns"))
    name_label = _coerce_str(cfg.get("name_label"), default="name").strip() or "name"
    value_label = _coerce_str(cfg.get("value_label"), default="value").strip() or "value"
    if not value_cols:
        errors.append(_bad_config(node_id, "Unpivot.value_columns is required."))
        return None
    cols_sql = ", ".join(f'"{c}"' for c in value_cols)
    return CompiledBlock(
        sql=(f'UNPIVOT {src} ON {cols_sql} INTO NAME "{name_label}" VALUE "{value_label}"'),
        output_schema=output_schema,
    )


def _infer_unpivot(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id
    upstream = input_schemas.get("in")
    name_label = _coerce_str(cfg.get("name_label"), default="name").strip() or "name"
    value_label = _coerce_str(cfg.get("value_label"), default="value").strip() or "value"
    if upstream is None or upstream.unknown:
        return _unknown_schema()
    value_cols = set(_coerce_str_list(cfg.get("value_columns")))
    kept = [c for c in upstream.columns if c.name not in value_cols]
    return PinSchema(
        kind="table",
        columns=[
            *kept,
            ColumnSpec(name=name_label, duckdb_type="VARCHAR", nullable=False),
            ColumnSpec(name=value_label, duckdb_type="DOUBLE", nullable=True),
        ],
    )


register_block(
    type_name="Unpivot",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_unpivot,
    infer_fn=_infer_unpivot,
)


# --------------------------------------------------------------------- Union


def _compile_union(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    left = inputs.get("left")
    right = inputs.get("right")
    if not left or not right:
        errors.append(_bad_config(node_id, "Union requires both 'left' and 'right' inputs."))
        return None
    all_kw = "ALL " if bool(cfg.get("all")) else ""
    return CompiledBlock(
        sql=f"SELECT * FROM {left} UNION {all_kw}SELECT * FROM {right}",
        output_schema=output_schema,
    )


def _infer_set_op(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    errors: list[CompileError],
    *,
    label: str,
) -> PinSchema:
    """Infer a set operation's output — the shared left==right column rule.

    UNION / EXCEPT / INTERSECT all require the two inputs to expose the same
    ordered column-name list and yield that list; a mismatch is surfaced on the
    ``right`` pin and degrades the downstream schema to unknown so dependent
    blocks do not validate against a column set that will never materialise.
    """
    left = input_schemas.get("left")
    right = input_schemas.get("right")
    if left is None or right is None:
        return _unknown_schema()
    left_names = [c.name for c in left.columns]
    right_names = [c.name for c in right.columns]
    if left_names != right_names:
        errors.append(
            CompileError(
                kind="type_mismatch",
                node_id=node_id,
                pin="right",
                message=(
                    f"{label} upstream column lists differ: "
                    f"left={left_names!r} right={right_names!r}"
                ),
            )
        )
        return _unknown_schema()
    return left


def _infer_union(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg
    return _infer_set_op(node_id, input_schemas, errors, label="Union")


register_block(
    type_name="Union",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_union,
    infer_fn=_infer_union,
)


# --------------------------------------------------------------------- Except / Intersect


def _compile_except(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    del cfg
    left = inputs.get("left")
    right = inputs.get("right")
    if not left or not right:
        errors.append(_bad_config(node_id, "Except requires both 'left' and 'right' inputs."))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {left} EXCEPT SELECT * FROM {right}",
        output_schema=output_schema,
    )


def _infer_except(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg
    return _infer_set_op(node_id, input_schemas, errors, label="Except")


def _compile_intersect(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    del cfg
    left = inputs.get("left")
    right = inputs.get("right")
    if not left or not right:
        errors.append(_bad_config(node_id, "Intersect requires both 'left' and 'right' inputs."))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {left} INTERSECT SELECT * FROM {right}",
        output_schema=output_schema,
    )


def _infer_intersect(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg
    return _infer_set_op(node_id, input_schemas, errors, label="Intersect")


register_block(
    type_name="Except",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_except,
    infer_fn=_infer_except,
)


register_block(
    type_name="Intersect",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_intersect,
    infer_fn=_infer_intersect,
)


# --------------------------------------------------------------------- Unnest


def _list_element_type(duckdb_type: str) -> str | None:
    """Return the element type of a DuckDB list type, or None if not a list.

    DuckDB spells list types two ways — ``INTEGER[]`` and ``LIST(INTEGER)`` —
    so Unnest strips either wrapper to learn what the exploded column holds; a
    non-list (or unparseable) type yields None so the caller can fall back to
    an unknown output schema rather than guessing.
    """
    t = (duckdb_type or "").strip()
    if t.endswith("[]"):
        return t[:-2].strip() or None
    if t.upper().startswith("LIST(") and t.endswith(")"):
        return t[5:-1].strip() or None
    return None


def _compile_unnest(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Unnest requires an upstream input."))
        return None
    column = _coerce_str(cfg.get("column")).strip()
    if not column:
        errors.append(_bad_config(node_id, "Unnest.column is required."))
        return None
    if bool(cfg.get("with_ordinality")):
        ordinality_alias = (
            _coerce_str(cfg.get("ordinality_alias"), default="ordinality").strip() or "ordinality"
        )
        return CompiledBlock(
            sql=(
                f'SELECT * EXCLUDE ("{column}"), '
                f'UNNEST("{column}") AS "{column}", '
                f'generate_subscripts("{column}", 1) AS "{ordinality_alias}" '
                f"FROM {src}"
            ),
            output_schema=output_schema,
        )
    return CompiledBlock(
        sql=f'SELECT * EXCLUDE ("{column}"), UNNEST("{column}") AS "{column}" FROM {src}',
        output_schema=output_schema,
    )


def _infer_unnest(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    upstream = input_schemas.get("in")
    if upstream is None or upstream.unknown:
        return _unknown_schema()
    column = _coerce_str(cfg.get("column")).strip()
    if not column:
        return _unknown_schema()
    cols = {c.name: c for c in upstream.columns}
    if column not in cols:
        errors.append(
            CompileError(
                kind="type_mismatch",
                node_id=node_id,
                pin="in",
                column=column,
                message=f"Unnest column {column!r} not in upstream schema.",
            )
        )
        return _unknown_schema()
    elem = _list_element_type(cols[column].duckdb_type)
    unknown = False
    new_cols: list[ColumnSpec] = []
    for col in upstream.columns:
        if col.name != column:
            new_cols.append(col)
        elif elem is not None:
            new_cols.append(ColumnSpec(name=column, duckdb_type=elem, nullable=True))
        else:
            # Column is not a parseable list type — keep it but flag the output
            # unknown so downstream blocks do not over-trust the element type.
            new_cols.append(col)
            unknown = True
    if bool(cfg.get("with_ordinality")):
        ordinality_alias = (
            _coerce_str(cfg.get("ordinality_alias"), default="ordinality").strip() or "ordinality"
        )
        new_cols.append(ColumnSpec(name=ordinality_alias, duckdb_type="BIGINT", nullable=False))
    return PinSchema(kind="table", columns=new_cols, unknown=unknown)


register_block(
    type_name="Unnest",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_unnest,
    infer_fn=_infer_unnest,
)


# --------------------------------------------------------------------- Distinct


def _compile_distinct(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Distinct requires an upstream input."))
        return None
    columns = _coerce_str_list(cfg.get("columns"))
    if columns:
        cols_sql = ", ".join(f'"{c}"' for c in columns)
        return CompiledBlock(
            sql=f"SELECT DISTINCT ON ({cols_sql}) * FROM {src}",
            output_schema=output_schema,
        )
    return CompiledBlock(
        sql=f"SELECT DISTINCT * FROM {src}",
        output_schema=output_schema,
    )


def _infer_distinct(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg, errors, node_id
    return input_schemas.get("in", _unknown_schema())


register_block(
    type_name="Distinct",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_distinct,
    infer_fn=_infer_distinct,
)


# --------------------------------------------------------------------- Sort


def _compile_sort(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Sort requires an upstream input."))
        return None
    order_by = cfg.get("order_by") or []
    clauses: list[str] = []
    for entry in order_by:
        if isinstance(entry, str):
            clauses.append(f'"{entry}" ASC')
        elif isinstance(entry, dict):
            col = str(entry.get("column") or "").strip()
            direction = str(entry.get("direction") or "asc").upper()
            if direction not in {"ASC", "DESC"}:
                direction = "ASC"
            if col:
                clauses.append(f'"{col}" {direction}')
    if not clauses:
        errors.append(_bad_config(node_id, "Sort.order_by must list at least one column."))
        return None
    return CompiledBlock(
        sql=f"SELECT * FROM {src} ORDER BY {', '.join(clauses)}",
        output_schema=output_schema,
    )


def _infer_sort(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg, errors, node_id
    return input_schemas.get("in", _unknown_schema())


register_block(
    type_name="Sort",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_sort,
    infer_fn=_infer_sort,
)


# --------------------------------------------------------------------- Sample


def _compile_sample(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Sample requires an upstream input."))
        return None
    kind = _coerce_str(cfg.get("kind"), default="percent").lower().strip()
    raw_value = cfg.get("value")
    try:
        value = float(raw_value) if raw_value is not None else 0.0
    except TypeError, ValueError:
        errors.append(_bad_config(node_id, "Sample.value must be numeric."))
        return None
    if kind == "percent":
        return CompiledBlock(
            sql=f"SELECT * FROM {src} USING SAMPLE {value} PERCENT",
            output_schema=output_schema,
        )
    if kind == "rows":
        return CompiledBlock(
            sql=f"SELECT * FROM {src} USING SAMPLE {int(value)} ROWS",
            output_schema=output_schema,
        )
    errors.append(_bad_config(node_id, "Sample.kind must be 'percent' or 'rows'."))
    return None


def _infer_sample(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg, errors, node_id
    return input_schemas.get("in", _unknown_schema())


register_block(
    type_name="Sample",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_sample,
    infer_fn=_infer_sample,
)
