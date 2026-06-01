# pyright: reportPrivateUsage=false
"""Column-level blocks for the visual data-product canvas.

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
    _register,
    _unknown_schema,
)
from pointlessql.services.dp_canvas._types import ColumnSpec, CompileError, PinSchema

# --------------------------------------------------------------------- Cast


_DUCKDB_TYPES: tuple[str, ...] = (
    "VARCHAR",
    "TEXT",
    "BIGINT",
    "INTEGER",
    "INT",
    "SMALLINT",
    "DOUBLE",
    "REAL",
    "DECIMAL",
    "BOOLEAN",
    "DATE",
    "TIMESTAMP",
    "TIME",
    "BLOB",
)


def _is_known_duckdb_type(t: str) -> bool:
    base = t.upper().split("(")[0].strip()
    return base in _DUCKDB_TYPES


def _compile_cast(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Cast requires an upstream input."))
        return None
    casts = cfg.get("casts") or []
    by_column: dict[str, str] = {}
    for entry in casts:
        if not isinstance(entry, dict):
            continue
        col = str(entry.get("column") or "").strip()
        ttype = str(entry.get("target_type") or "").strip()
        if not col or not ttype:
            continue
        if not _is_known_duckdb_type(ttype):
            errors.append(
                CompileError(
                    kind="bad_config",
                    node_id=node_id,
                    pin=None,
                    column=col,
                    actual_type=ttype,
                    suggestion="UNKNOWN_DUCKDB_TYPE",
                    message=f"Cast target_type {ttype!r} not a known DuckDB type.",
                )
            )
            return None
        by_column[col] = ttype
    if not by_column:
        errors.append(
            _bad_config(node_id, "Cast.casts must declare at least one column-to-type pair.")
        )
        return None
    projections = ", ".join(f'"{col}"::{tt} AS "{col}"' for col, tt in by_column.items())
    return CompiledBlock(
        sql=f"SELECT *, {projections} FROM {src}",
        output_schema=output_schema,
    )


def _infer_cast(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id
    upstream = input_schemas.get("in")
    if upstream is None or upstream.unknown:
        return _unknown_schema()
    by_col = {
        str(e.get("column") or "").strip(): str(e.get("target_type") or "").strip()
        for e in (cfg.get("casts") or [])
        if isinstance(e, dict)
    }
    out_cols = [
        ColumnSpec(name=c.name, duckdb_type=by_col.get(c.name, c.duckdb_type), nullable=c.nullable)
        for c in upstream.columns
    ]
    return PinSchema(kind="table", columns=out_cols)


_register(
    BlockSpec(type_name="Cast", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- Rename


def _compile_rename(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "Rename requires an upstream input."))
        return None
    renames = cfg.get("renames") or {}
    if not isinstance(renames, dict) or not renames:
        errors.append(_bad_config(node_id, "Rename.renames must be a non-empty {old: new} dict."))
        return None
    parts = [f'"{old}" AS "{new}"' for old, new in renames.items() if old and new]
    if not parts:
        errors.append(_bad_config(node_id, "Rename.renames empty after cleaning."))
        return None
    return CompiledBlock(
        sql=f"SELECT *, {', '.join(parts)} FROM {src}",
        output_schema=output_schema,
    )


def _infer_rename(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id
    upstream = input_schemas.get("in")
    if upstream is None or upstream.unknown:
        return _unknown_schema()
    renames = cfg.get("renames") or {}
    if not isinstance(renames, dict):
        return upstream
    out_cols = [
        ColumnSpec(
            name=renames.get(c.name, c.name),
            duckdb_type=c.duckdb_type,
            nullable=c.nullable,
        )
        for c in upstream.columns
    ]
    return PinSchema(kind="table", columns=out_cols)


_register(
    BlockSpec(type_name="Rename", input_pins=(("in", "table"),), output_pins=(("out", "table"),))
)


# --------------------------------------------------------------------- CalcColumn


def _compile_calc_column(
    node_id: str,
    inputs: dict[str, str],
    output_schema: PinSchema,
    cfg: dict[str, Any],
    errors: list[CompileError],
) -> CompiledBlock | None:
    src = inputs.get("in")
    if not src:
        errors.append(_bad_config(node_id, "CalcColumn requires an upstream input."))
        return None
    expression = _coerce_str(cfg.get("expression")).strip()
    alias = _coerce_str(cfg.get("target_alias")).strip()
    if not expression or not alias:
        errors.append(_bad_config(node_id, "CalcColumn.expression and target_alias are required."))
        return None
    return CompiledBlock(
        sql=f'SELECT *, ({expression}) AS "{alias}" FROM {src}',
        output_schema=output_schema,
    )


def _infer_calc_column(
    node_id: str,
    input_schemas: dict[str, PinSchema],
    cfg: dict[str, Any],
    errors: list[CompileError],
    *,
    seed: PinSchema | None,
) -> PinSchema:
    del seed, errors, node_id
    upstream = input_schemas.get("in")
    alias = _coerce_str(cfg.get("target_alias")).strip() or "calc"
    if upstream is None or upstream.unknown:
        return PinSchema(
            kind="table",
            columns=[ColumnSpec(name=alias, duckdb_type="UNKNOWN", nullable=True)],
            unknown=True,
        )
    new_col = ColumnSpec(name=alias, duckdb_type="UNKNOWN", nullable=True)
    return PinSchema(kind="table", columns=[*upstream.columns, new_col])


_register(
    BlockSpec(
        type_name="CalcColumn",
        input_pins=(("in", "table"),),
        output_pins=(("out", "table"),),
    )
)



_COMPILE_DISPATCH.update(
    {
        "Cast": _compile_cast,
        "Rename": _compile_rename,
        "CalcColumn": _compile_calc_column,
    }
)
_INFER_DISPATCH.update(
    {
        "Cast": _infer_cast,
        "Rename": _infer_rename,
        "CalcColumn": _infer_calc_column,
    }
)