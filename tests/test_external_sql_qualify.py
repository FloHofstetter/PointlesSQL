"""default catalog/schema qualification."""

from __future__ import annotations

import pytest
import sqlglot

from pointlessql.services.sql_statements._qualify import qualify_sql


def _norm(sql: str) -> str:
    """Roundtrip through sqlglot for whitespace-insensitive comparison."""
    return sqlglot.parse_one(sql, read="duckdb").sql(dialect="duckdb")


def test_qualify_no_defaults_returns_input_unchanged() -> None:
    sql = "SELECT * FROM main.sales.orders"
    assert qualify_sql(sql, default_catalog=None, default_schema=None) == sql


def test_qualify_two_part_ref_gets_catalog_prefix() -> None:
    out = qualify_sql(
        "SELECT * FROM sales.orders",
        default_catalog="main",
        default_schema=None,
    )
    assert _norm(out) == _norm("SELECT * FROM main.sales.orders")


def test_qualify_one_part_ref_gets_catalog_and_schema() -> None:
    out = qualify_sql(
        "SELECT id FROM orders",
        default_catalog="main",
        default_schema="sales",
    )
    assert _norm(out) == _norm("SELECT id FROM main.sales.orders")


def test_qualify_three_part_ref_left_alone() -> None:
    out = qualify_sql(
        "SELECT * FROM prod.silver.fact",
        default_catalog="main",
        default_schema="sales",
    )
    assert _norm(out) == _norm("SELECT * FROM prod.silver.fact")


def test_qualify_one_part_without_both_defaults_left_alone() -> None:
    """1-part refs need BOTH defaults; with only catalog set we leave the
    ref alone so the downstream parser raises a clear 2-part error."""
    out = qualify_sql(
        "SELECT * FROM orders",
        default_catalog="main",
        default_schema=None,
    )
    assert "orders" in out  # untouched (sqlglot may rewrite whitespace)


def test_qualify_parse_error_propagates() -> None:
    with pytest.raises(sqlglot.errors.ParseError):
        qualify_sql(
            "SELEC * FROM x",  # typo
            default_catalog="main",
            default_schema="sales",
        )
