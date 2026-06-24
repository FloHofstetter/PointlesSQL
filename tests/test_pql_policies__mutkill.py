"""Mutation-kill tests for ``pointlessql.pql._policies``.

Pins the row-filter validation and ``current_user()`` substitution
behaviours the broader ``test_pql_policies.py`` suite executed but did not
detect mutations in — most importantly the single-quote SQL-escaping in
``substitute_current_user`` (an injection-relevant path) and the
empty-predicate rejection in ``validate_row_filter``.
"""

from __future__ import annotations

import pytest

from pointlessql.pql._policies import substitute_current_user, validate_row_filter


def test_substitute_current_user_with_no_principal_yields_empty_literal() -> None:
    """A missing principal substitutes an empty string literal, not a placeholder."""
    # kills (principal or "") -> (principal or "XXXX")
    assert substitute_current_user("current_user()", None) == "''"


def test_substitute_current_user_sql_escapes_single_quotes() -> None:
    """A principal containing a single quote is doubled (SQL-escaped)."""
    # kills .replace("'", "''") -> .replace("XX'XX", "''") and -> .replace("'", "XX''XX")
    assert substitute_current_user("current_user()", "o'brien") == "'o''brien'"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_validate_row_filter_rejects_blank_predicate(blank: str | None) -> None:
    """Empty / whitespace / ``None`` predicates raise with the non-empty message."""
    # kills (predicate or "") -> "XXXX", ValueError(None), and the upper-cased message
    with pytest.raises(ValueError, match="non-empty"):
        validate_row_filter(blank)  # type: ignore[arg-type]
