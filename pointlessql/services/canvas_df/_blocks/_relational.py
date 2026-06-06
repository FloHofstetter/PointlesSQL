# pyright: reportPrivateUsage=false
"""Relational blocks for the visual data-product canvas.

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
    _coerce_str_list,
    _schema_columns,
    _unknown_schema,
    register_block,
)
from pointlessql.services.canvas_df._types import ColumnSpec, CompileError, PinSchema

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


register_block(
    type_name="Filter",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_filter,
    infer_fn=_infer_filter,
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
                    column=col,
                    message=f"Project column {col!r} not in upstream schema.",
                )
            )
            continue
        out_cols.append(spec)
    return PinSchema(kind="table", columns=out_cols)


register_block(
    type_name="Project",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_project,
    infer_fn=_infer_project,
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
                        column=key,
                        message=f"Join key {key!r} not in left schema.",
                    )
                )
            if key not in right_cols:
                errors.append(
                    CompileError(
                        kind="type_mismatch",
                        node_id=node_id,
                        pin="right",
                        column=key,
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


register_block(
    type_name="Join",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_join,
    infer_fn=_infer_join,
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
                    column=key,
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


register_block(
    type_name="GroupBy",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_group_by,
    infer_fn=_infer_group_by,
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


register_block(
    type_name="Limit",
    input_pins=(("in", "table"),),
    output_pins=(("out", "table"),),
    compile_fn=_compile_limit,
    infer_fn=_infer_limit,
)


# --------------------------------------------------------------------- SemiJoin / AntiJoin


def _compile_exists_join(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    label: str,
    negate: bool,
) -> CompiledBlock | None:
    """Compile a semi- or anti-join — filter ``left`` rows by a match in ``right``.

    Neither widens the row: the result is exactly ``left``'s columns, kept
    (semi, ``EXISTS``) or dropped (anti, ``NOT EXISTS``) according to whether a
    key-matched ``right`` row exists.  This is the cheap way to express "rows
    of A that (do not) appear in B" without the duplicate-blowup of a join.
    """
    left = inputs.get("left")
    right = inputs.get("right")
    if not left or not right:
        errors.append(
            CompileError(
                kind="missing_input",
                node_id=node_id,
                pin="left" if not left else "right",
                message=f"{label} requires both 'left' and 'right' inputs.",
            )
        )
        return None
    keys = _coerce_str_list(cfg.get("keys"))
    if not keys:
        errors.append(_bad_config(node_id, f"{label}.keys is required (non-empty list)."))
        return None
    cond = " AND ".join(f'l."{key}" = r."{key}"' for key in keys)
    exists_kw = "NOT EXISTS" if negate else "EXISTS"
    return CompiledBlock(
        sql=(
            f"SELECT l.* FROM {left} l "
            f"WHERE {exists_kw} (SELECT 1 FROM {right} r WHERE {cond})"
        ),
        output_schema=output_schema,
    )


def _infer_exists_join(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    label: str,
) -> PinSchema:
    left = input_schemas.get("left")
    right = input_schemas.get("right")
    if left is None or right is None:
        return _unknown_schema()
    keys = _coerce_str_list(cfg.get("keys"))
    if not keys:
        return _unknown_schema()
    if not left.unknown and not right.unknown:
        left_cols = _schema_columns(left)
        right_cols = _schema_columns(right)
        for key in keys:
            if key not in left_cols:
                errors.append(
                    CompileError(
                        kind="type_mismatch",
                        node_id=node_id,
                        pin="left",
                        column=key,
                        message=f"{label} key {key!r} not in left schema.",
                    )
                )
            if key not in right_cols:
                errors.append(
                    CompileError(
                        kind="type_mismatch",
                        node_id=node_id,
                        pin="right",
                        column=key,
                        message=f"{label} key {key!r} not in right schema.",
                    )
                )
    return left


def _compile_semi_join(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    return _compile_exists_join(
        node_id, inputs, output_schema, cfg, errors, label="SemiJoin", negate=False
    )


def _infer_semi_join(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    return _infer_exists_join(node_id, input_schemas, cfg, errors, label="SemiJoin")


def _compile_anti_join(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    return _compile_exists_join(
        node_id, inputs, output_schema, cfg, errors, label="AntiJoin", negate=True
    )


def _infer_anti_join(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed
    return _infer_exists_join(node_id, input_schemas, cfg, errors, label="AntiJoin")


register_block(
    type_name="SemiJoin",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_semi_join,
    infer_fn=_infer_semi_join,
)


register_block(
    type_name="AntiJoin",
    input_pins=(("left", "table"), ("right", "table")),
    output_pins=(("out", "table"),),
    compile_fn=_compile_anti_join,
    infer_fn=_infer_anti_join,
)