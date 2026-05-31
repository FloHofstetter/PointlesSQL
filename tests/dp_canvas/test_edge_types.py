"""Unit tests for the edge-type categoriser."""

from __future__ import annotations

from pointlessql.services.dp_canvas._edge_types import (
    categorize_columns,
    categorize_pin_schema,
)
from pointlessql.services.dp_canvas._types import ColumnSpec, PinSchema


def _col(name: str, t: str) -> ColumnSpec:
    return ColumnSpec(name=name, duckdb_type=t)


def test_all_numeric_returns_numeric() -> None:
    cols = [_col("a", "BIGINT"), _col("b", "DECIMAL(10,2)"), _col("c", "DOUBLE")]
    assert categorize_columns(cols) == "numeric"


def test_all_text_returns_text() -> None:
    cols = [_col("a", "VARCHAR"), _col("b", "TEXT")]
    assert categorize_columns(cols) == "text"


def test_temporal_dominant() -> None:
    cols = [_col("a", "TIMESTAMP"), _col("b", "DATE"), _col("c", "VARCHAR")]
    assert categorize_columns(cols) == "temporal"


def test_tie_returns_mixed() -> None:
    cols = [_col("a", "INT"), _col("b", "VARCHAR")]
    assert categorize_columns(cols) == "mixed"


def test_empty_returns_mixed() -> None:
    assert categorize_columns([]) == "mixed"


def test_unknown_pin_schema_returns_mixed() -> None:
    assert categorize_pin_schema(PinSchema(unknown=True)) == "mixed"


def test_none_pin_schema_returns_mixed() -> None:
    assert categorize_pin_schema(None) == "mixed"


def test_complex_types_bucket() -> None:
    cols = [_col("a", "STRUCT(x INT)"), _col("b", "LIST(INT)")]
    assert categorize_columns(cols) == "complex"
