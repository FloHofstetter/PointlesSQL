"""Property tests for the PQL SQL parser's reference extraction.

Grant scoping depends on the parser enumerating every touched table: an
identifier or statement-shape edge case that under-counts references could
silently let a query read a table the caller was never granted. These
Hypothesis properties fuzz quoting / reserved-word / dotted identifiers
across SELECT / JOIN / CTE / subquery / INSERT shapes against the four
invariants the scoping layer relies on.
"""

from __future__ import annotations

import pytest
from hypothesis import given

from pointlessql.pql.sql_parser._parse import parse_and_classify
from pointlessql.pql.sql_parser._prepare import prepare_sql
from pointlessql.pql.sql_parser._refs import extract_source_refs, extract_write_target
from tests.sql_parser_verify import strategies as strat

pytestmark = pytest.mark.sql_parser_verify


@given(strat.join_select())
def test_refs_are_deduped_in_first_seen_order(case: tuple[str, list[str]]) -> None:
    """``prepare_sql().refs`` lists each table once, in first-appearance order."""
    sql, expected = case
    refs = prepare_sql(sql).refs
    assert refs == expected
    assert len(refs) == len(set(refs))


@given(strat.subquery_select())
def test_subquery_refs_are_enumerated(case: tuple[str, list[str]]) -> None:
    """A table inside a derived-table subquery is still enumerated, deduped.

    The completeness invariant (no table under-counted) is what scoping
    relies on; the relative order of a nested subquery vs. a sibling JOIN
    is a parser-internal traversal detail, so it is not pinned here.
    """
    sql, expected = case
    refs = prepare_sql(sql).refs
    assert set(refs) == set(expected)
    assert len(refs) == len(set(refs))


@given(strat.cte_shadow_select())
def test_cte_alias_shadowing_a_table_is_not_a_ref(case: tuple[str, list[str]]) -> None:
    """A CTE alias that shadows a real table's bare name is not counted."""
    sql, expected = case
    assert prepare_sql(sql).refs == expected


@given(strat.insert_select())
def test_write_target_excluded_from_source_refs(case: tuple[str, str, str]) -> None:
    """The write target is reported exactly and excluded from the source refs."""
    sql, target, source = case
    ast, stype = parse_and_classify(sql)
    assert extract_write_target(ast, stype) == target
    sources = extract_source_refs(ast, stype)
    assert target not in sources
    assert source in sources


@given(strat.join_select())
def test_prepare_refs_are_stable(case: tuple[str, list[str]]) -> None:
    """Preparing the same SQL twice yields identical refs (no hidden state)."""
    sql, _expected = case
    assert prepare_sql(sql).refs == prepare_sql(sql).refs
