"""Unit test for the Sprint-57 Delta→UC type mapping."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pointlessql.api.main import _DELTA_PRIMITIVE_TO_UC, _delta_field_to_uc


def _fake_field(primitive: str) -> SimpleNamespace:
    """Return an object shaped like ``deltalake.Field`` for mapping tests."""
    return SimpleNamespace(type=SimpleNamespace(type=primitive))


@pytest.mark.parametrize(
    ("delta_type", "expected"),
    [
        ("long", ("LONG", "long")),
        ("double", ("DOUBLE", "double")),
        ("string", ("STRING", "string")),
        ("boolean", ("BOOLEAN", "boolean")),
        ("date", ("DATE", "date")),
        ("timestamp", ("TIMESTAMP", "timestamp")),
        ("integer", ("INT", "int")),
    ],
)
def test_delta_field_to_uc_covers_all_primitives(
    delta_type: str, expected: tuple[str, str]
) -> None:
    assert _delta_field_to_uc(_fake_field(delta_type)) == expected


def test_delta_field_to_uc_defaults_to_string_on_unknown() -> None:
    # Compound types (structs, arrays) stringify to something that is
    # not a recognised primitive.  The mapper falls back to STRING.
    assert _delta_field_to_uc(_fake_field("struct<x:long>")) == ("STRING", "string")
    # Non-str primitives (shouldn't happen but be defensive).
    assert _delta_field_to_uc(SimpleNamespace(type=SimpleNamespace(type=None))) == (
        "STRING",
        "string",
    )


def test_mapping_constant_covers_the_common_set() -> None:
    # Sanity: the canonical primitive codes land in the map so adding
    # a new one shows up as a failing test instead of a silent fallback.
    for key in ("long", "double", "string", "boolean", "date"):
        assert key in _DELTA_PRIMITIVE_TO_UC
