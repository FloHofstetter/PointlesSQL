"""Unit tests for the canvas column-level blocks (Cast / Rename / CalcColumn).

These exercise the compile error branches (missing input, empty / invalid
config) and the schema-inference paths through the public
``compile_block`` / ``infer_block`` dispatch — pure functions, no DB.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.dp_canvas._blocks import compile_block, infer_block
from pointlessql.services.dp_canvas._types import ColumnSpec, PinSchema


def _schema(*cols: tuple[str, str]) -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[ColumnSpec(name=n, duckdb_type=t, nullable=True) for n, t in cols],
    )


_UNKNOWN = PinSchema(kind="table", columns=[], unknown=True)
_OUT = _schema(("a", "INT"))


def _compile(block_type: str, inputs: dict[str, str], cfg: dict[str, Any]):
    errors: list[Any] = []
    result = compile_block(
        block_type=block_type,
        node_id="n1",
        inputs=inputs,
        output_schema=_OUT,
        cfg=cfg,
        errors=errors,
    )
    return result, errors


def _infer(block_type: str, schemas: dict[str, PinSchema], cfg: dict[str, Any]) -> PinSchema:
    return infer_block(
        block_type=block_type, node_id="n1", input_schemas=schemas, cfg=cfg, errors=[]
    )


# --- Cast -----------------------------------------------------------------


def test_cast_missing_input_errors() -> None:
    result, errors = _compile("Cast", {}, {"casts": [{"column": "a", "target_type": "INT"}]})
    assert result is None
    assert any("upstream" in e.message for e in errors)


def test_cast_no_valid_pairs_errors() -> None:
    result, errors = _compile("Cast", {"in": "cte0"}, {"casts": [{"column": "", "target_type": ""}]})
    assert result is None
    assert any("at least one" in e.message for e in errors)


def test_cast_infer_unknown_upstream() -> None:
    out = _infer("Cast", {"in": _UNKNOWN}, {"casts": []})
    assert out.unknown


def test_cast_infer_applies_target_type() -> None:
    out = _infer(
        "Cast",
        {"in": _schema(("a", "INT"), ("b", "VARCHAR"))},
        {"casts": [{"column": "a", "target_type": "BIGINT"}]},
    )
    by = {c.name: c.duckdb_type for c in out.columns}
    assert by["a"] == "BIGINT"
    assert by["b"] == "VARCHAR"


# --- Rename ---------------------------------------------------------------


def test_rename_missing_input_errors() -> None:
    result, errors = _compile("Rename", {}, {"renames": {"a": "b"}})
    assert result is None
    assert any("upstream" in e.message for e in errors)


def test_rename_empty_dict_errors() -> None:
    result, errors = _compile("Rename", {"in": "cte0"}, {"renames": {}})
    assert result is None
    assert any("non-empty" in e.message for e in errors)


def test_rename_blank_pairs_error() -> None:
    result, errors = _compile("Rename", {"in": "cte0"}, {"renames": {"": "x"}})
    assert result is None
    assert errors


def test_rename_infer_renames_columns() -> None:
    out = _infer("Rename", {"in": _schema(("a", "INT"))}, {"renames": {"a": "alpha"}})
    assert [c.name for c in out.columns] == ["alpha"]


def test_rename_infer_unknown_upstream() -> None:
    assert _infer("Rename", {"in": _UNKNOWN}, {"renames": {"a": "b"}}).unknown


# --- CalcColumn -----------------------------------------------------------


def test_calc_missing_input_errors() -> None:
    result, errors = _compile("CalcColumn", {}, {"expression": "a+1", "target_alias": "x"})
    assert result is None
    assert any("upstream" in e.message for e in errors)


def test_calc_missing_expression_or_alias_errors() -> None:
    result, errors = _compile("CalcColumn", {"in": "cte0"}, {"expression": "", "target_alias": "x"})
    assert result is None
    assert any("required" in e.message for e in errors)


def test_calc_compiles_expression() -> None:
    result, errors = _compile(
        "CalcColumn", {"in": "cte0"}, {"expression": "a + 1", "target_alias": "x"}
    )
    assert errors == []
    assert result is not None
    assert '(a + 1) AS "x"' in result.sql


def test_calc_infer_appends_column() -> None:
    out = _infer(
        "CalcColumn", {"in": _schema(("a", "INT"))}, {"expression": "a+1", "target_alias": "doubled"}
    )
    assert [c.name for c in out.columns] == ["a", "doubled"]


def test_calc_infer_unknown_upstream_uses_alias() -> None:
    out = _infer("CalcColumn", {"in": _UNKNOWN}, {"target_alias": "z"})
    assert out.unknown
    assert out.columns[0].name == "z"
