"""Sanity tests for :class:`pointlessql.table_fqn.TableFqn`.

The validation type subclasses ``str`` so DB columns, JSON wire
format, and f-string interpolation must produce the underlying
string verbatim.  These tests pin those contracts BEFORE any
producer or consumer migrates so a regression here fails CI
loudly rather than silently corrupting an audit row.
"""

from __future__ import annotations

import json

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.table_fqn import TableFqn


def test_parse_strips_whitespace_around_segments() -> None:
    """``parse`` strips per-segment whitespace before validation."""
    fqn = TableFqn.parse("  cat  .  sch  .  tbl  ")
    assert fqn.parts() == ("cat", "sch", "tbl")


def test_parse_rejects_two_part_name() -> None:
    """A two-part name fails validation with :class:`ValidationError`."""
    with pytest.raises(ValidationError):
        TableFqn.parse("cat.sch")


def test_parse_rejects_empty_segment() -> None:
    """``a..c`` fails validation — middle segment is empty."""
    with pytest.raises(ValidationError):
        TableFqn.parse("cat..tbl")


def test_parse_rejects_empty_string() -> None:
    """The empty string fails validation."""
    with pytest.raises(ValidationError):
        TableFqn.parse("")


def test_from_parts_skips_validation() -> None:
    """``from_parts`` is the unvalidated factory."""
    fqn = TableFqn.from_parts("cat", "sch", "tbl")
    assert fqn == "cat.sch.tbl"
    assert fqn.parts() == ("cat", "sch", "tbl")


def test_subclass_identity() -> None:
    """``TableFqn`` is-a ``str`` so SQLAlchemy / JSON absorb it."""
    fqn = TableFqn.parse("cat.sch.tbl")
    assert isinstance(fqn, str) is True
    assert isinstance(fqn, TableFqn) is True


def test_json_round_trip_serialises_underlying_string() -> None:
    """``json.dumps`` produces the bare string, not a class repr."""
    fqn = TableFqn.parse("cat.sch.tbl")
    assert json.dumps({"target": fqn}) == '{"target": "cat.sch.tbl"}'


def test_str_interpolation_yields_underlying_string() -> None:
    """f-string + concatenation both produce the underlying string."""
    fqn = TableFqn.parse("cat.sch.tbl")
    assert f"got {fqn}" == "got cat.sch.tbl"
    assert "got " + fqn == "got cat.sch.tbl"


def test_segment_properties_match_parts() -> None:
    """``.catalog`` / ``.schema`` / ``.table`` align with ``.parts()``."""
    fqn = TableFqn.parse("cat.sch.tbl")
    assert fqn.catalog == "cat"
    assert fqn.schema == "sch"
    assert fqn.table == "tbl"


def test_equality_to_plain_str() -> None:
    """Membership in ``TableFqn`` is identical to membership-by-string."""
    assert TableFqn.parse("cat.sch.tbl") == "cat.sch.tbl"
    assert TableFqn.from_parts("cat", "sch", "tbl") == "cat.sch.tbl"
