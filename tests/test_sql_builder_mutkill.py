"""Mutation-killing tests for the visual query builder.

Pins the SELECT SQL generated from builder state, the best-effort
inverse parse, and the literal/operator mappings — including the
shapes the parser deliberately rejects (multi-table, subqueries,
non-3-part tables).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from pointlessql.services.sql.builder import (
    SUPPORTED_AGGS,
    SUPPORTED_OPS,
    build_sql_from_state,
    parse_sql_to_state,
)


def _build(**state: Any) -> str:
    state.setdefault("table_fqn", "c.s.t")
    return build_sql_from_state(state)


def _ws(sql: str) -> str:
    """Collapse whitespace so fragment assertions ignore pretty-print."""
    return re.sub(r"\s+", " ", sql).strip()


def _one_filter(op: str, value: Any = None) -> str:
    f: dict[str, Any] = {"column": "x", "op": op}
    if value is not None:
        f["value"] = value
    return _ws(_build(filters=[f]))


# --- build: table + select shape -----------------------------------------


def test_build_bare_table_selects_star() -> None:
    assert _ws(_build()) == "SELECT * FROM c.s.t"


def test_build_missing_table_raises() -> None:
    with pytest.raises(ValueError) as ei:
        build_sql_from_state({"table_fqn": "  "})
    assert str(ei.value) == "table_fqn is required."


def test_build_non_three_part_table_raises() -> None:
    with pytest.raises(ValueError) as ei:
        build_sql_from_state({"table_fqn": "schema.table"})
    assert str(ei.value) == (
        "table_fqn must be three-part (catalog.schema.table); got 'schema.table'."
    )


def test_build_group_by_and_aggregates() -> None:
    sql = _ws(
        _build(
            group_by=["a", "b"],
            aggregates=[
                {"fn": "count", "column": "*", "alias": "n"},
                {"fn": "sum", "column": "x"},
            ],
        )
    )
    assert "a, b, COUNT(*) AS n, SUM(x)" in sql
    assert "GROUP BY a, b" in sql


def test_build_unsupported_aggregate_raises() -> None:
    with pytest.raises(ValueError) as ei:
        _build(aggregates=[{"fn": "MEDIAN", "column": "x"}])
    assert str(ei.value) == "Unsupported aggregate function: 'MEDIAN'"


def test_build_aggregate_without_column_uses_star() -> None:
    assert "COUNT(*)" in _ws(_build(aggregates=[{"fn": "count"}]))


def test_build_filter_without_op_defaults_to_equals() -> None:
    assert "x = 'v'" in _ws(_build(filters=[{"column": "x", "value": "v"}]))


def test_build_invalid_filter_does_not_drop_later_valid_filters() -> None:
    # A skipped (unsupported-op) filter must `continue`, not `break`,
    # so a following valid filter still lands in the WHERE clause.
    sql = _ws(
        _build(
            filters=[
                {"column": "x", "op": "BAD", "value": "1"},
                {"column": "y", "op": "=", "value": "k"},
            ]
        )
    )
    assert "y = 'k'" in sql
    assert "x" not in sql.split("WHERE", 1)[1]


# --- build: operators -----------------------------------------------------


@pytest.mark.parametrize(
    "op,value,fragment",
    [
        ("=", "v", "x = 'v'"),
        ("!=", "v", "x <> 'v'"),
        ("<", 5, "x < 5"),
        ("<=", 5, "x <= 5"),
        (">", 5, "x > 5"),
        (">=", 5, "x >= 5"),
        ("LIKE", "%x%", "x LIKE '%x%'"),
        ("ILIKE", "%x%", "x ILIKE '%x%'"),
        ("IN", "a,b", "x IN ('a', 'b')"),
    ],
)
def test_build_filter_operator(op: str, value: Any, fragment: str) -> None:
    assert fragment in _one_filter(op, value)


def test_build_is_null_and_is_not_null() -> None:
    assert "x IS NULL" in _one_filter("IS NULL")
    assert "NOT x IS NULL" in _one_filter("IS NOT NULL")


def test_build_bool_and_float_literals() -> None:
    assert "x = TRUE" in _one_filter("=", True)
    assert "x = 1.5" in _one_filter("=", 1.5)


@pytest.mark.parametrize("value", [None, ""])
def test_build_value_required_op_dropped_when_value_missing(value: Any) -> None:
    assert "WHERE" not in _build(filters=[{"column": "x", "op": "=", "value": value}])


def test_build_unsupported_op_dropped() -> None:
    assert "WHERE" not in _build(filters=[{"column": "x", "op": "BETWEEN", "value": "1"}])


def test_build_blank_column_dropped() -> None:
    assert "WHERE" not in _build(filters=[{"column": "  ", "op": "=", "value": "v"}])


def test_build_multiple_filters_are_anded() -> None:
    sql = _ws(
        _build(
            filters=[
                {"column": "a", "op": "=", "value": "v"},
                {"column": "b", "op": ">", "value": 3},
            ]
        )
    )
    assert "a = 'v'" in sql and "b > 3" in sql and " AND " in sql


# --- build: order by / limit ----------------------------------------------


def test_build_order_by_desc() -> None:
    assert "ORDER BY a DESC" in _ws(_build(order_by=[{"column": "a", "dir": "desc"}]))


def test_build_order_by_defaults_asc() -> None:
    # Ascending renders without DESC (sqlglot emits "a NULLS FIRST").
    asc = _ws(_build(order_by=[{"column": "a"}]))
    assert "ORDER BY a NULLS FIRST" in asc
    assert "DESC" not in asc


def test_build_limit_applied() -> None:
    assert "LIMIT 10" in _ws(_build(limit=10))


def test_build_limit_one_is_positive() -> None:
    # Guards the ``limit > 0`` boundary (a ``> 1`` mutant drops limit=1).
    assert "LIMIT 1" in _ws(_build(limit=1))


def test_build_order_by_blank_column_skipped() -> None:
    assert "ORDER BY" not in _build(order_by=[{"column": "   "}])


def test_build_order_by_invalid_entry_does_not_drop_later_valid() -> None:
    # Non-str column must `continue`, not `break`.
    sql = _ws(_build(order_by=[{"column": 123}, {"column": "good", "dir": "desc"}]))
    assert "ORDER BY good DESC" in sql


@pytest.mark.parametrize("limit", [0, -5, "10", None])
def test_build_limit_ignored_when_not_positive_int(limit: Any) -> None:
    assert "LIMIT" not in _build(limit=limit)


# --- parse: supported shapes ----------------------------------------------


def test_parse_simple_equality() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE a = 'v'")
    assert st is not None
    assert st["table_fqn"] == "c.s.t"
    assert st["filters"] == [{"column": "a", "op": "=", "value": "v"}]


def test_parse_numeric_value_is_int() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE b > 3")
    assert st["filters"] == [{"column": "b", "op": ">", "value": 3}]


def test_parse_conjunction_keeps_both() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE a = 'v' AND b > 3")
    assert {f["column"] for f in st["filters"]} == {"a", "b"}


def test_parse_is_null_variants() -> None:
    assert parse_sql_to_state("SELECT * FROM c.s.t WHERE c IS NULL")["filters"] == [
        {"column": "c", "op": "IS NULL", "value": None}
    ]
    assert parse_sql_to_state("SELECT * FROM c.s.t WHERE c IS NOT NULL")["filters"] == [
        {"column": "c", "op": "IS NOT NULL", "value": None}
    ]


def test_parse_in_list_of_numbers() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE d IN (1, 2, 3)")
    assert st["filters"] == [{"column": "d", "op": "IN", "value": [1, 2, 3]}]


def test_parse_like_clause() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE x LIKE '%a%'")
    assert st["filters"] == [{"column": "x", "op": "LIKE", "value": "%a%"}]


def test_parse_ilike_clause() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE x ILIKE '%a%'")
    assert st["filters"] == [{"column": "x", "op": "ILIKE", "value": "%a%"}]


def test_parse_float_value_is_float() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE x > 1.5")
    (f,) = st["filters"]
    assert f["value"] == 1.5
    assert isinstance(f["value"], float)


def test_parse_boolean_value() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE x = TRUE")
    assert st["filters"] == [{"column": "x", "op": "=", "value": True}]


def test_parse_quoted_numeric_stays_string() -> None:
    # A string literal that looks numeric is preserved as text, not
    # coerced to int.
    st = parse_sql_to_state("SELECT * FROM c.s.t WHERE x = '007'")
    (f,) = st["filters"]
    assert f["value"] == "007"
    assert isinstance(f["value"], str)


def test_parse_group_by_with_aggregate() -> None:
    st = parse_sql_to_state("SELECT col, COUNT(*) AS n FROM c.s.t GROUP BY col")
    assert st["group_by"] == ["col"]
    assert st["aggregates"] == [{"fn": "COUNT", "column": "*", "alias": "n"}]


def test_parse_aggregate_over_named_column() -> None:
    # SUM(x) keeps the real column name (not "*").
    st = parse_sql_to_state("SELECT SUM(x) AS s FROM c.s.t")
    assert st["aggregates"] == [{"fn": "SUM", "column": "x", "alias": "s"}]


def test_parse_order_by_and_limit() -> None:
    st = parse_sql_to_state("SELECT * FROM c.s.t ORDER BY a DESC LIMIT 10")
    assert st["order_by"] == [{"column": "a", "dir": "desc"}]
    assert st["limit"] == 10


# --- parse: rejected shapes -----------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM a.b.c JOIN d.e.f ON 1 = 1",  # multi-table
        "SELECT * FROM justone",  # not 3-part
        "SELECT (SELECT 1) FROM c.s.t",  # subquery select item
        "SELECT * FROM c.s.t WHERE bad LIKE col2",  # rhs not a literal
        "not even sql ((",  # unparseable
        "INSERT INTO c.s.t VALUES (1)",  # not a SELECT
    ],
)
def test_parse_rejects_unsupported(sql: str) -> None:
    assert parse_sql_to_state(sql) is None


def test_parse_bare_column_outside_group_by_rejected() -> None:
    # `extra` is selected but not grouped → builder can't represent it.
    assert parse_sql_to_state("SELECT a, extra FROM c.s.t GROUP BY a") is None


# --- round trips ----------------------------------------------------------


def test_round_trip_group_agg_order_limit() -> None:
    state = {
        "table_fqn": "c.s.t",
        "group_by": ["a"],
        "aggregates": [{"fn": "COUNT", "column": "*", "alias": "n"}],
        "order_by": [{"column": "a", "dir": "desc"}],
        "limit": 25,
    }
    reparsed = parse_sql_to_state(build_sql_from_state(state))
    assert reparsed["table_fqn"] == "c.s.t"
    assert reparsed["group_by"] == ["a"]
    assert reparsed["aggregates"] == [{"fn": "COUNT", "column": "*", "alias": "n"}]
    assert reparsed["order_by"] == [{"column": "a", "dir": "desc"}]
    assert reparsed["limit"] == 25


# --- module-level constants -----------------------------------------------


def test_supported_constants() -> None:
    assert SUPPORTED_AGGS == ("COUNT", "SUM", "AVG", "MIN", "MAX")
    assert "IS NOT NULL" in SUPPORTED_OPS and "ILIKE" in SUPPORTED_OPS
