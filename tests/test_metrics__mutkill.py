"""Mutation-kill tests for ``pointlessql.pql._metrics``.

These pin behaviours the broader ``test_pql_metrics.py`` suite only
exercised incidentally, so a mutant could slip through. The clearest
example: the existing statement-smuggling test feeds ``1; DROP TABLE x``
and matches on ``measure 'evil'`` — but that input is *also* rejected by
the ``exp.Command`` guard, so the dedicated ``';'`` check stayed
unverified. A benign ``sum(a); sum(b)`` (which ``parse_one`` would
silently truncate) is the case only the ``';'`` guard catches.
"""

from __future__ import annotations

import pytest

from pointlessql.pql._metrics import _parse_fragment, compile_metric_query

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


# --------------------------------------------------------------------------
# _parse_fragment
# --------------------------------------------------------------------------


def test_parse_fragment_strips_only_trailing_semicolon() -> None:
    """A trailing ``;`` is stripped (not whitespace-only, not left-stripped)."""
    # kills rstrip(";") -> rstrip(None) / lstrip(";")
    assert _parse_fragment("sum(amount);", what="measure").sql(dialect="duckdb") == "SUM(amount)"


def test_parse_fragment_keeps_a_single_uppercase_identifier() -> None:
    """``rstrip(';')`` must not also strip trailing characters like ``X``."""
    # kills rstrip(";") -> rstrip("X;"): the latter would reduce "X" to ""
    assert _parse_fragment("X", what="measure").sql(dialect="duckdb") == "X"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_parse_fragment_rejects_blank(blank: str | None) -> None:
    """Empty / whitespace / ``None`` fragments raise, never fall through."""
    # kills (fragment or "") -> (fragment or "XXXX")
    with pytest.raises(ValueError, match="non-empty"):
        _parse_fragment(blank, what="measure")  # type: ignore[arg-type]


def test_parse_fragment_rejects_internal_semicolon_even_when_benign() -> None:
    """A benign ``a; b`` is rejected by the ';' guard, not just the Command guard."""
    # kills `if ";" in candidate` -> `if "XX;XX" in candidate`
    with pytest.raises(ValueError, match="single expression"):
        _parse_fragment("sum(a); sum(b)", what="measure")


# --------------------------------------------------------------------------
# compile_metric_query
# --------------------------------------------------------------------------


def test_dimension_expr_is_embedded_verbatim() -> None:
    """The dimension's own expression is compiled, not ``str(None)``."""
    # kills str(d["expr"]) -> str(None)
    sql = compile_metric_query(
        source_table=SOURCE, spec=SPEC, dimensions=["order_month"], measures=["revenue"]
    )
    # the dimension's expr (date_trunc over ordered_at) is present, not str(None)
    assert "DATE_TRUNC" in sql.upper()
    assert "ordered_at" in sql
    assert "None" not in sql


def test_spec_without_dimensions_key_compiles() -> None:
    """A spec missing the ``dimensions`` key still compiles a measures-only query."""
    # kills spec.get("dimensions", []) -> spec.get("dimensions", None) (TypeError)
    spec = {"measures": [{"name": "revenue", "expr": "sum(amount)"}]}
    sql = compile_metric_query(source_table=SOURCE, spec=spec, dimensions=[], measures=["revenue"])
    assert "SUM(AMOUNT)" in sql.upper()


def test_spec_without_measures_key_raises_value_error() -> None:
    """A spec missing the ``measures`` key raises ValueError, not TypeError."""
    # kills spec.get("measures", []) -> spec.get("measures", None) (TypeError)
    spec = {"dimensions": []}
    with pytest.raises(ValueError, match="unknown measure"):
        compile_metric_query(source_table=SOURCE, spec=spec, dimensions=[], measures=["revenue"])


def test_order_by_on_a_selected_dimension_is_allowed() -> None:
    """A selected dimension is a valid order_by target."""
    # kills selected_names.append(name) -> selected_names.append(None)
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue"],
        order_by="region asc",
    )
    assert 'ORDER BY "region" ASC' in sql


def test_order_by_without_direction_defaults_to_asc() -> None:
    """An order_by with only a name defaults to ascending (a valid direction)."""
    # kills else "asc" -> "ASC"/"XXascXX" (which would fail the direction check)
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue"],
        order_by="revenue",
    )
    assert 'ORDER BY "revenue" ASC' in sql


def test_order_by_accepts_explicit_asc() -> None:
    """An explicit ``asc`` direction is accepted (the valid set is lowercase)."""
    # kills ("asc", "desc") -> ("ASC"/"XXascXX", "desc")
    sql = compile_metric_query(
        source_table=SOURCE,
        spec=SPEC,
        dimensions=["region"],
        measures=["revenue"],
        order_by="revenue asc",
    )
    assert 'ORDER BY "revenue" ASC' in sql


def test_limit_boundary_zero_rejected_one_allowed() -> None:
    """``limit <= 0`` is rejected at exactly 0; ``limit == 1`` is allowed."""
    # kills `<= 0` -> `< 0` (0 must raise) and `<= 0` -> `<= 1` (1 must pass)
    with pytest.raises(ValueError, match="positive"):
        compile_metric_query(
            source_table=SOURCE, spec=SPEC, dimensions=[], measures=["revenue"], limit=0
        )
    sql = compile_metric_query(
        source_table=SOURCE, spec=SPEC, dimensions=[], measures=["revenue"], limit=1
    )
    assert "LIMIT 1" in sql


def test_invalid_dimension_expr_error_names_the_dimension() -> None:
    """A rejected dimension fragment's error identifies it as a dimension."""
    # kills what=f"dimension {name!r}" -> what=None
    spec = {
        "dimensions": [{"name": "bad", "expr": "(SELECT 1)"}],
        "measures": [{"name": "r", "expr": "sum(x)"}],
    }
    with pytest.raises(ValueError, match="dimension"):
        compile_metric_query(source_table=SOURCE, spec=spec, dimensions=["bad"], measures=["r"])


def test_invalid_spec_filter_error_names_the_spec_filter() -> None:
    """A rejected spec filter's error identifies it as the spec filter (exact wording)."""
    # kills what="spec filter" -> what=None and -> "SPEC FILTER"
    spec = {
        "dimensions": [],
        "measures": [{"name": "r", "expr": "sum(x)"}],
        "filter": "(SELECT 1)",
    }
    with pytest.raises(ValueError, match="spec filter"):
        compile_metric_query(source_table=SOURCE, spec=spec, dimensions=[], measures=["r"])
