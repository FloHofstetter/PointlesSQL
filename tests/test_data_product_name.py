"""Sanity tests for :class:`pointlessql.data_products.DataProductRef`.

Same shape as ``tests/test_table_fqn.py`` — pin the
``str``-subclass identity, the JSON wire format, and the
parse/from_parts contracts so any regression at the boundary is
caught at unit-test time.
"""

from __future__ import annotations

import json

import pytest

from pointlessql.data_products import DataProductRef
from pointlessql.exceptions import ValidationError


def test_parse_returns_two_part_ref() -> None:
    """``parse`` accepts a clean two-part name and exposes parts."""
    ref = DataProductRef.parse("main.sales_gold")
    assert ref == "main.sales_gold"
    assert ref.parts() == ("main", "sales_gold")
    assert ref.catalog == "main"
    assert ref.schema == "sales_gold"


def test_parse_strips_whitespace() -> None:
    """Each segment's leading/trailing whitespace is stripped."""
    ref = DataProductRef.parse("  main  .  sales_gold  ")
    assert ref.parts() == ("main", "sales_gold")


def test_parse_rejects_three_parts() -> None:
    """A three-part name (table FQN) is rejected."""
    with pytest.raises(ValidationError, match="two-part"):
        DataProductRef.parse("main.sales.orders")


def test_parse_rejects_one_part() -> None:
    """A bare schema name is rejected."""
    with pytest.raises(ValidationError, match="two-part"):
        DataProductRef.parse("sales_gold")


def test_parse_rejects_empty_segment() -> None:
    """``a..b`` and trailing dots are rejected."""
    with pytest.raises(ValidationError):
        DataProductRef.parse("main.")
    with pytest.raises(ValidationError):
        DataProductRef.parse(".sales_gold")
    with pytest.raises(ValidationError):
        DataProductRef.parse("")


def test_from_parts_skips_validation() -> None:
    """``from_parts`` is the caller-checked path; no validation."""
    ref = DataProductRef.from_parts("main", "sales_gold")
    assert ref == "main.sales_gold"


def test_subclass_identity() -> None:
    """A :class:`DataProductRef` is-a ``str`` for runtime checks."""
    ref = DataProductRef.parse("main.sales_gold")
    assert isinstance(ref, str)


def test_json_round_trip() -> None:
    """JSON serialisation produces the underlying string verbatim."""
    ref = DataProductRef.parse("main.sales_gold")
    assert json.dumps(ref) == '"main.sales_gold"'


def test_f_string_interpolation() -> None:
    """f-string interpolation produces the underlying string."""
    ref = DataProductRef.parse("main.sales_gold")
    assert f"product={ref}" == "product=main.sales_gold"


def test_equality_with_plain_str() -> None:
    """Equality with a bare str works (subclass semantics)."""
    ref = DataProductRef.parse("main.sales_gold")
    assert ref == "main.sales_gold"
