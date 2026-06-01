# pyright: reportPrivateUsage=false
"""Reshape blocks for the visual data-product canvas.

Compile + schema-inference helpers split out of the former single-file
block registry.  Shared infrastructure and the public dispatch live in
:mod:`pointlessql.services.dp_canvas._blocks._base`; this module
registers its block types into the dispatch tables at import time.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.dp_canvas._blocks._base import (
    _COMPILE_DISPATCH,
    _INFER_DISPATCH,
    BlockSpec,
    CompiledBlock,
    _bad_config,
    _coerce_str,
    _coerce_str_list,
    _register,
    _unknown_schema,
)
from pointlessql.services.dp_canvas._types import ColumnSpec, CompileError, PinSchema

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
    partition_sql = (
        f"PARTITION BY {', '.join(f'"{c}"' for c in partition)} " if partition else ""
    )
    order_sql = f"ORDER BY {', '.join(f'"{c}"' for c in order)} " if order else ""
    over = f"({partition_sql}{order_sql}".rstrip() + ")"
    return CompiledBlock(
        sql=f"SELECT *, {fn.upper()}({args_sql}) OVER {over} AS \"{alias}\" FROM {src}",
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


_register(
    BlockSpec(type_name="Window", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
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
        sql=(
            f'PIVOT {src} ON "{on_col}" USING {agg_sql}"{value_col}"{suffix}'
        ),
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


_register(
    BlockSpec(type_name="Pivot", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
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
        sql=(
            f'UNPIVOT {src} ON {cols_sql} INTO NAME "{name_label}" VALUE "{value_label}"'
        ),
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


_register(
    BlockSpec(type_name="Unpivot", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
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


def _infer_union(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, cfg
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
                    "Union upstream column lists differ: "
                    f"left={left_names!r} right={right_names!r}"
                ),
            )
        )
        return _unknown_schema()
    return left


_register(
    BlockSpec(
        type_name="Union",
        input_pins=(("left", "table"), ("right", "table")),
        output_pins=(("out", "table"),),
    )
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


_register(
    BlockSpec(type_name="Distinct", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
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


_register(
    BlockSpec(type_name="Sort", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
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
    except (TypeError, ValueError):
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


_register(
    BlockSpec(type_name="Sample", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)



_COMPILE_DISPATCH.update(
    {
        "Window": _compile_window,
        "Pivot": _compile_pivot,
        "Unpivot": _compile_unpivot,
        "Union": _compile_union,
        "Distinct": _compile_distinct,
        "Sort": _compile_sort,
        "Sample": _compile_sample,
    }
)
_INFER_DISPATCH.update(
    {
        "Window": _infer_window,
        "Pivot": _infer_pivot,
        "Unpivot": _infer_unpivot,
        "Union": _infer_union,
        "Distinct": _infer_distinct,
        "Sort": _infer_sort,
        "Sample": _infer_sample,
    }
)