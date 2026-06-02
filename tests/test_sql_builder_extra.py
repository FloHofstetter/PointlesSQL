"""Additional unit tests for the visual SQL builder's translation logic.

Targets the filter-operator and literal branches plus the build-side
validation that the existing ``test_sql_builder`` suite leaves uncovered.
All pure (sqlglot only, no DB).
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.services.sql.builder import (
    _filter_to_expression,
    _literal,
    build_sql_from_state,
)


def _sql(**state: Any) -> str:
    base: dict[str, Any] = {"table_fqn": "main.s.t"}
    base.update(state)
    return build_sql_from_state(base)


# --- build_sql validation -------------------------------------------------


def test_missing_table_fqn_raises() -> None:
    with pytest.raises(ValueError, match="table_fqn is required"):
        build_sql_from_state({})


def test_non_three_part_table_raises() -> None:
    with pytest.raises(ValueError, match="three-part"):
        build_sql_from_state({"table_fqn": "main.s"})


def test_unsupported_aggregate_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported aggregate"):
        _sql(aggregates=[{"fn": "median", "column": "x"}])


# --- filter operators through build_sql ----------------------------------


def test_is_null_filter() -> None:
    assert "IS NULL" in _sql(filters=[{"column": "a", "op": "IS NULL"}])


def test_is_not_null_filter() -> None:
    out = _sql(filters=[{"column": "a", "op": "IS NOT NULL"}])
    assert "NOT" in out and "IS NULL" in out


def test_in_filter_from_csv_string() -> None:
    out = _sql(filters=[{"column": "a", "op": "IN", "value": "x, y, z"}])
    assert "IN (" in out


def test_like_and_ilike_filters() -> None:
    assert "LIKE" in _sql(filters=[{"column": "a", "op": "LIKE", "value": "%x%"}])
    assert "ILIKE" in _sql(filters=[{"column": "a", "op": "ILIKE", "value": "%x%"}])


def test_comparison_filters() -> None:
    out = _sql(filters=[{"column": "n", "op": ">", "value": 5}])
    assert ">" in out and "5" in out


def test_empty_value_filter_is_skipped() -> None:
    # An "=" filter with an empty value contributes no WHERE clause.
    out = _sql(filters=[{"column": "a", "op": "=", "value": ""}])
    assert "WHERE" not in out


# --- aggregates / group-by / order / limit -------------------------------


def test_group_by_with_aliased_aggregate() -> None:
    out = _sql(
        group_by=["country"],
        aggregates=[{"fn": "count", "column": "*", "alias": "n"}],
    )
    assert "GROUP BY" in out
    assert "COUNT(*)" in out
    assert '"n"' in out or " AS n" in out.upper() or "AS N" in out.upper()


def test_order_by_desc_and_limit() -> None:
    out = _sql(order_by=[{"column": "a", "dir": "desc"}], limit=10)
    assert "ORDER BY" in out
    assert "DESC" in out.upper()
    assert "LIMIT 10" in out


# --- _filter_to_expression direct ----------------------------------------


def test_filter_in_from_list() -> None:
    node = _filter_to_expression("a", "IN", ["x", "y"])
    assert node is not None
    assert "IN" in node.sql()


def test_filter_in_non_sequence_is_none() -> None:
    assert _filter_to_expression("a", "IN", 5) is None


def test_filter_missing_value_is_none() -> None:
    assert _filter_to_expression("a", "=", None) is None


def test_filter_unknown_op_is_none() -> None:
    assert _filter_to_expression("a", "BETWEEN", 5) is None


# --- _literal direct ------------------------------------------------------


def test_literal_bool() -> None:
    assert "TRUE" in _literal(True).sql().upper()


def test_literal_number() -> None:
    assert _literal(42).sql() == "42"


def test_literal_float() -> None:
    assert "1.5" in _literal(1.5).sql()


def test_literal_string_is_quoted() -> None:
    assert _literal("hi").sql() == "'hi'"
