"""Tests for the metric-view SQL compiler."""

from __future__ import annotations

import pytest

from pointlessql.pql._metrics import compile_metric_query

SPEC = {
    "dimensions": [
        {"name": "region", "expr": "region"},
        {"name": "order_month", "expr": "date_trunc('month', ordered_at)"},
    ],
    "measures": [
        {"name": "revenue", "expr": "sum(amount)"},
        {"name": "orders", "expr": "count(*)"},
    ],
    "filter": "status = 'completed'",
}

SOURCE = "shop.gold.orders"


def test_compiles_dimensions_measures_and_group_by() -> None:
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue", "orders"],
    )
    assert '"region"' in sql
    assert 'SUM(amount) AS "revenue"' in sql
    assert 'COUNT(*) AS "orders"' in sql
    assert "FROM shop.gold.orders" in sql
    assert "GROUP BY 1" in sql
    assert "status = 'completed'" in sql


def test_grand_total_has_no_group_by() -> None:
    sql = compile_metric_query(source_table=SOURCE, spec=SPEC, dimensions=[], measures=["revenue"])
    assert "GROUP BY" not in sql


def test_extra_where_is_anded_with_spec_filter() -> None:
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue"],
        where="region = 'emea'",
    )
    assert "status = 'completed'" in sql
    assert "region = 'emea'" in sql
    assert " AND " in sql


def test_order_by_and_limit() -> None:
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue"],
        order_by="revenue desc",
        limit=5,
    )
    assert 'ORDER BY "revenue" DESC' in sql
    assert "LIMIT 5" in sql


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"dimensions": ["nope"], "measures": ["revenue"]}, "unknown dimension"),
        ({"dimensions": [], "measures": ["nope"]}, "unknown measure"),
        ({"dimensions": [], "measures": []}, "at least one measure"),
        (
            {"dimensions": ["region"], "measures": ["revenue"], "order_by": "hax desc"},
            "order_by",
        ),
        (
            {"dimensions": ["region"], "measures": ["revenue"], "limit": -3},
            "limit",
        ),
        (
            {"dimensions": ["region"], "measures": ["revenue"], "where": "1 = 1; DROP TABLE x"},
            "where",
        ),
    ],
)
def test_rejects_malformed_queries(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        compile_metric_query(source_table=SOURCE, spec=SPEC, **kwargs)


def test_rejects_two_part_source() -> None:
    with pytest.raises(ValueError, match="catalog.schema.table"):
        compile_metric_query(
            source_table="gold.orders", spec=SPEC, dimensions=[], measures=["revenue"]
        )


def test_rejects_statement_smuggling_in_spec_expr() -> None:
    # statement separators never belong in a lone expression…
    bad = {"dimensions": [], "measures": [{"name": "evil", "expr": "1; DROP TABLE x"}]}
    with pytest.raises(ValueError, match="measure 'evil'"):
        compile_metric_query(source_table=SOURCE, spec=bad, dimensions=[], measures=["evil"])
    # …and neither do scalar subqueries — a measure must aggregate the
    # source table, not smuggle reads of other tables past the picker.
    subquery = {
        "dimensions": [],
        "measures": [{"name": "evil", "expr": "(SELECT secret FROM other.schema.tbl)"}],
    }
    with pytest.raises(ValueError, match="plain expression"):
        compile_metric_query(source_table=SOURCE, spec=subquery, dimensions=[], measures=["evil"])
