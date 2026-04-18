"""Unit tests for the Phase-12 SQL parser."""

from __future__ import annotations

import pytest

from pointlessql.pql.sql_parser import (
    SQLParseError,
    extract_table_refs,
    prepare_sql,
)


def test_simple_select_extracts_single_ref() -> None:
    refs = extract_table_refs("SELECT * FROM main.sales.orders")
    assert refs == ["main.sales.orders"]


def test_join_extracts_both_refs_in_order() -> None:
    refs = extract_table_refs(
        "SELECT o.* FROM main.sales.orders o "
        "JOIN main.sales.customers c ON o.cid = c.id"
    )
    assert refs == ["main.sales.orders", "main.sales.customers"]


def test_cte_alias_is_skipped() -> None:
    # The CTE body reads main.sales.orders; the outer SELECT references
    # the alias ``x`` which must not leak into the enforcement list.
    refs = extract_table_refs(
        "WITH x AS (SELECT * FROM main.sales.orders) SELECT * FROM x"
    )
    assert refs == ["main.sales.orders"]


def test_subquery_reference_is_extracted() -> None:
    refs = extract_table_refs(
        "SELECT * FROM (SELECT * FROM main.sales.orders) q"
    )
    assert refs == ["main.sales.orders"]


def test_duplicate_references_appear_once() -> None:
    refs = extract_table_refs(
        "SELECT a.*, b.* FROM main.sales.orders a, main.sales.orders b"
    )
    assert refs == ["main.sales.orders"]


def test_select_without_tables_returns_empty_list() -> None:
    assert extract_table_refs("SELECT 1 AS n") == []


def test_two_part_reference_raises() -> None:
    with pytest.raises(SQLParseError, match="catalog.schema.table"):
        extract_table_refs("SELECT * FROM sales.orders")


def test_malformed_sql_raises() -> None:
    with pytest.raises(SQLParseError, match="Could not parse SQL"):
        extract_table_refs("SELEC * FROM x")


def test_multi_statement_raises() -> None:
    with pytest.raises(SQLParseError, match="one SQL statement"):
        extract_table_refs("SELECT 1; SELECT 2")


def test_insert_is_rejected() -> None:
    with pytest.raises(SQLParseError, match="SELECT"):
        extract_table_refs("INSERT INTO main.a.b VALUES (1)")


def test_empty_sql_raises() -> None:
    with pytest.raises(SQLParseError, match="Empty"):
        extract_table_refs("")
    with pytest.raises(SQLParseError, match="Empty"):
        extract_table_refs("   \n  ")


def test_prepare_rewrites_three_part_to_quoted_identifier() -> None:
    prepared = prepare_sql("SELECT * FROM main.sales.orders LIMIT 5")
    assert prepared.refs == ["main.sales.orders"]
    # The rewritten form uses a single quoted identifier that
    # DuckDB can bind via conn.register(full_name, ...).
    assert '"main.sales.orders"' in prepared.rewritten_sql
    assert "main.sales.orders" in prepared.rewritten_sql


def test_prepare_preserves_alias() -> None:
    prepared = prepare_sql(
        "SELECT o.id FROM main.sales.orders o WHERE o.id > 0"
    )
    assert prepared.refs == ["main.sales.orders"]
    # Alias ``o`` must survive the rewrite so the column reference
    # ``o.id`` still binds at execution time.
    assert '"main.sales.orders" AS o' in prepared.rewritten_sql
