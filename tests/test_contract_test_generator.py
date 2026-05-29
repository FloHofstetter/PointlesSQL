"""Synthetic-data generator (Phase 142)."""

from __future__ import annotations

import pytest

from pointlessql.services.contract_tests import generate_arrow_table


def test_generates_requested_row_count() -> None:
    table = generate_arrow_table(
        [{"column": "email", "kind": "email"}],
        row_count=25,
    )
    assert table.num_rows == 25
    assert table.column_names == ["email"]


def test_generator_is_deterministic_with_same_seed() -> None:
    spec = [
        {"column": "x", "kind": "int", "min": 0, "max": 100},
        {"column": "y", "kind": "float", "min": 0.0, "max": 1.0},
    ]
    one = generate_arrow_table(spec, row_count=5, seed=42)
    two = generate_arrow_table(spec, row_count=5, seed=42)
    assert one.to_pylist() == two.to_pylist()


def test_different_seeds_produce_different_rows() -> None:
    spec = [{"column": "x", "kind": "int", "min": 0, "max": 10000}]
    a = generate_arrow_table(spec, row_count=10, seed=1)
    b = generate_arrow_table(spec, row_count=10, seed=2)
    assert a.to_pylist() != b.to_pylist()


def test_choice_kind_requires_non_empty_choices() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        generate_arrow_table(
            [{"column": "tier", "kind": "choice", "choices": []}],
            row_count=5,
        )


def test_unknown_kind_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown generator"):
        generate_arrow_table(
            [{"column": "bogus", "kind": "not_a_real_kind"}],
            row_count=5,
        )


def test_iso8601_kind_emits_parseable_timestamps() -> None:
    import datetime

    table = generate_arrow_table(
        [{"column": "created", "kind": "iso8601_ts", "since_days": 7}],
        row_count=10,
        seed=0,
    )
    values = table["created"].to_pylist()
    parsed = [datetime.datetime.fromisoformat(v) for v in values]
    assert all(p.tzinfo is not None for p in parsed)


def test_spec_from_json_string_works() -> None:
    table = generate_arrow_table(
        '[{"column": "n", "kind": "int", "min": 1, "max": 5}]',
        row_count=8,
        seed=0,
    )
    assert table.num_rows == 8
    assert set(table["n"].to_pylist()).issubset(set(range(1, 6)))


def test_empty_spec_returns_empty_table() -> None:
    table = generate_arrow_table([], row_count=3)
    assert table.num_rows == 0
    assert table.num_columns == 0
