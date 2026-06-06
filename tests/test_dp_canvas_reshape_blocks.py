"""Unit tests for the canvas reshape blocks.

Window / Pivot / Unpivot / Union / Distinct / Sort / Sample compile error
branches + schema-inference paths, driven through the public
``compile_block`` / ``infer_block`` dispatch. Pure functions, no DB.
"""

from __future__ import annotations

from typing import Any

from pointlessql.services.dp_canvas._blocks import compile_block, infer_block
from pointlessql.services.dp_canvas._types import ColumnSpec, PinSchema


def _schema(*cols: str) -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[ColumnSpec(name=n, duckdb_type="INT", nullable=True) for n in cols],
    )


_UNKNOWN = PinSchema(kind="table", columns=[], unknown=True)
_OUT = _schema("a")


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


def _infer(block_type: str, schemas: dict[str, PinSchema], cfg: dict[str, Any]):
    errors: list[Any] = []
    out = infer_block(
        block_type=block_type, node_id="n1", input_schemas=schemas, cfg=cfg, errors=errors
    )
    return out, errors


# --- Window ---------------------------------------------------------------


def test_window_missing_input() -> None:
    result, errors = _compile("Window", {}, {"function": "row_number", "target_alias": "rn"})
    assert result is None and errors


def test_window_bad_function() -> None:
    result, errors = _compile("Window", {"in": "c0"}, {"function": "bogus", "target_alias": "x"})
    assert result is None
    assert any("must be one of" in e.message for e in errors)


def test_window_missing_alias() -> None:
    result, errors = _compile("Window", {"in": "c0"}, {"function": "rank"})
    assert result is None
    assert any("target_alias" in e.message for e in errors)


def test_window_infer_rank_is_bigint() -> None:
    out, _ = _infer("Window", {"in": _schema("a")}, {"function": "rank", "target_alias": "r"})
    assert out.columns[-1].name == "r"
    assert out.columns[-1].duckdb_type == "BIGINT"


def test_window_infer_unknown_upstream() -> None:
    out, _ = _infer("Window", {"in": _UNKNOWN}, {"function": "rank", "target_alias": "r"})
    assert out.unknown


# --- Pivot ----------------------------------------------------------------


def test_pivot_missing_input() -> None:
    result, _ = _compile("Pivot", {}, {"on_column": "a", "value_column": "b"})
    assert result is None


def test_pivot_missing_columns() -> None:
    result, errors = _compile("Pivot", {"in": "c0"}, {"on_column": "", "value_column": ""})
    assert result is None
    assert any("required" in e.message for e in errors)


def test_pivot_bad_aggregate() -> None:
    result, errors = _compile(
        "Pivot", {"in": "c0"}, {"on_column": "a", "value_column": "b", "aggregate": "median"}
    )
    assert result is None
    assert any("not supported" in e.message for e in errors)


def test_pivot_compiles() -> None:
    result, errors = _compile(
        "Pivot", {"in": "c0"}, {"on_column": "a", "value_column": "b", "aggregate": "sum"}
    )
    assert errors == [] and result is not None
    assert "PIVOT c0" in result.sql


def test_pivot_infer_is_unknown() -> None:
    out, _ = _infer("Pivot", {"in": _schema("a")}, {})
    assert out.unknown


# --- Unpivot --------------------------------------------------------------


def test_unpivot_missing_input() -> None:
    result, _ = _compile("Unpivot", {}, {"value_columns": ["a"]})
    assert result is None


def test_unpivot_missing_value_columns() -> None:
    result, errors = _compile("Unpivot", {"in": "c0"}, {"value_columns": []})
    assert result is None
    assert any("value_columns" in e.message for e in errors)


def test_unpivot_infer_keeps_non_value_cols() -> None:
    out, _ = _infer(
        "Unpivot",
        {"in": _schema("id", "x", "y")},
        {"value_columns": ["x", "y"], "name_label": "k", "value_label": "v"},
    )
    names = [c.name for c in out.columns]
    assert names == ["id", "k", "v"]


# --- Union ----------------------------------------------------------------


def test_union_missing_input() -> None:
    result, errors = _compile("Union", {"left": "c0"}, {})
    assert result is None
    assert any("both" in e.message for e in errors)


def test_union_compiles_all() -> None:
    result, errors = _compile("Union", {"left": "c0", "right": "c1"}, {"all": True})
    assert errors == [] and result is not None
    assert "UNION ALL" in result.sql


def test_union_infer_column_mismatch_errors() -> None:
    out, errors = _infer("Union", {"left": _schema("a"), "right": _schema("b")}, {})
    assert out.unknown
    assert any(e.kind == "type_mismatch" for e in errors)


def test_union_infer_match_returns_left() -> None:
    out, errors = _infer("Union", {"left": _schema("a"), "right": _schema("a")}, {})
    assert errors == []
    assert [c.name for c in out.columns] == ["a"]


# --- Distinct / Sort / Sample --------------------------------------------


def test_distinct_missing_input() -> None:
    result, _ = _compile("Distinct", {}, {})
    assert result is None


def test_distinct_with_and_without_columns() -> None:
    with_cols, _ = _compile("Distinct", {"in": "c0"}, {"columns": ["a"]})
    without, _ = _compile("Distinct", {"in": "c0"}, {})
    assert "DISTINCT ON" in with_cols.sql
    assert "SELECT DISTINCT *" in without.sql


def test_sort_no_clauses_errors() -> None:
    result, errors = _compile("Sort", {"in": "c0"}, {"order_by": []})
    assert result is None
    assert any("at least one" in e.message for e in errors)


def test_sort_mixed_entries() -> None:
    result, errors = _compile(
        "Sort", {"in": "c0"}, {"order_by": ["a", {"column": "b", "direction": "desc"}]}
    )
    assert errors == []
    assert '"a" ASC' in result.sql
    assert '"b" DESC' in result.sql


def test_sample_non_numeric_value() -> None:
    result, errors = _compile("Sample", {"in": "c0"}, {"kind": "percent", "value": "abc"})
    assert result is None
    assert any("numeric" in e.message for e in errors)


def test_sample_bad_kind() -> None:
    result, errors = _compile("Sample", {"in": "c0"}, {"kind": "weird", "value": 5})
    assert result is None
    assert any("percent" in e.message for e in errors)


def test_sample_percent_and_rows() -> None:
    pct, _ = _compile("Sample", {"in": "c0"}, {"kind": "percent", "value": 10})
    rows, _ = _compile("Sample", {"in": "c0"}, {"kind": "rows", "value": 100})
    assert "SAMPLE 10.0 PERCENT" in pct.sql
    assert "SAMPLE 100 ROWS" in rows.sql


# --- Except / Intersect ---------------------------------------------------


def test_except_missing_input() -> None:
    result, errors = _compile("Except", {"left": "c0"}, {})
    assert result is None
    assert any("both" in e.message for e in errors)


def test_except_compiles() -> None:
    result, errors = _compile("Except", {"left": "c0", "right": "c1"}, {})
    assert errors == [] and result is not None
    assert result.sql == "SELECT * FROM c0 EXCEPT SELECT * FROM c1"


def test_intersect_compiles() -> None:
    result, errors = _compile("Intersect", {"left": "c0", "right": "c1"}, {})
    assert errors == [] and result is not None
    assert result.sql == "SELECT * FROM c0 INTERSECT SELECT * FROM c1"


def test_except_infer_column_mismatch_errors() -> None:
    out, errors = _infer("Except", {"left": _schema("a"), "right": _schema("b")}, {})
    assert out.unknown
    assert any(e.kind == "type_mismatch" and e.pin == "right" for e in errors)
    assert any("Except" in e.message for e in errors)


def test_intersect_infer_match_returns_left() -> None:
    out, errors = _infer("Intersect", {"left": _schema("a"), "right": _schema("a")}, {})
    assert errors == []
    assert [c.name for c in out.columns] == ["a"]


# --- Unnest ---------------------------------------------------------------


def _list_schema(col: str, duckdb_type: str) -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[ColumnSpec(name=col, duckdb_type=duckdb_type, nullable=True)],
    )


def test_unnest_missing_input() -> None:
    result, errors = _compile("Unnest", {}, {"column": "tags"})
    assert result is None
    assert any("upstream" in e.message for e in errors)


def test_unnest_missing_column() -> None:
    result, errors = _compile("Unnest", {"in": "c0"}, {})
    assert result is None
    assert any("column is required" in e.message for e in errors)


def test_unnest_compiles_plain() -> None:
    result, errors = _compile("Unnest", {"in": "c0"}, {"column": "tags"})
    assert errors == [] and result is not None
    assert result.sql == 'SELECT * EXCLUDE ("tags"), UNNEST("tags") AS "tags" FROM c0'


def test_unnest_compiles_with_ordinality() -> None:
    result, _ = _compile(
        "Unnest",
        {"in": "c0"},
        {"column": "tags", "with_ordinality": True, "ordinality_alias": "pos"},
    )
    assert 'generate_subscripts("tags", 1) AS "pos"' in result.sql


def test_unnest_infer_unwraps_list_element() -> None:
    out, errors = _infer("Unnest", {"in": _list_schema("tags", "INTEGER[]")}, {"column": "tags"})
    assert errors == []
    assert not out.unknown
    assert [(c.name, c.duckdb_type) for c in out.columns] == [("tags", "INTEGER")]


def test_unnest_infer_missing_column_errors() -> None:
    out, errors = _infer("Unnest", {"in": _schema("a")}, {"column": "tags"})
    assert out.unknown
    assert any(e.kind == "type_mismatch" and e.column == "tags" for e in errors)


def test_unnest_infer_non_list_marks_unknown() -> None:
    out, _ = _infer("Unnest", {"in": _list_schema("tags", "VARCHAR")}, {"column": "tags"})
    assert out.unknown


def test_unnest_infer_appends_ordinality_column() -> None:
    out, _ = _infer(
        "Unnest",
        {"in": _list_schema("tags", "LIST(BIGINT)")},
        {"column": "tags", "with_ordinality": True, "ordinality_alias": "pos"},
    )
    names = [c.name for c in out.columns]
    assert names == ["tags", "pos"]
    assert out.columns[0].duckdb_type == "BIGINT"
    assert out.columns[1].duckdb_type == "BIGINT"


def test_list_element_type_parses_both_spellings() -> None:
    from pointlessql.services.canvas_df._blocks._reshape import _list_element_type

    assert _list_element_type("INTEGER[]") == "INTEGER"
    assert _list_element_type("LIST(BIGINT)") == "BIGINT"
    assert _list_element_type("list(varchar)") == "varchar"
    assert _list_element_type("VARCHAR") is None
    assert _list_element_type("") is None
