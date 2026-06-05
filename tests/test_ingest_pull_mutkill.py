"""Mutation-killing tests for the ingest pull-mapping pure helpers.

Covers mapping validation/normalisation, the high-water incremental
SQL wrappers, and the table-mappings JSON load/dump round-trip.
"""

from __future__ import annotations

from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest.connectors import ReaderSpec
from pointlessql.services.ingest.pull import (
    _coerce_mapping,
    _max_high_water_sql,
    _wrap_with_high_water,
    dump_mappings,
    load_mappings,
)

_SPEC = ReaderSpec(sql="SELECT * FROM read_csv_auto('x');")


# --- _coerce_mapping ------------------------------------------------------


def test_coerce_full_mode_normalises() -> None:
    out = _coerce_mapping({"source_table": " s ", "target_fqn": "c.s.t", "mode": "full"})
    assert out == {
        "source_table": "s",
        "target_fqn": "c.s.t",
        "mode": "full",
        "high_water_col": None,
        "last_high_water_value": None,
    }


def test_coerce_mode_defaults_to_full() -> None:
    out = _coerce_mapping({"target_fqn": "c.s.t"})
    assert out["mode"] == "full"


def test_coerce_incremental_keeps_high_water() -> None:
    out = _coerce_mapping(
        {
            "target_fqn": "c.s.t",
            "mode": "incremental",
            "high_water_col": "ts",
            "last_high_water_value": "5",
        }
    )
    assert out["high_water_col"] == "ts"
    assert out["last_high_water_value"] == "5"


def test_coerce_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError, match="Mapping mode must be one of"):
        _coerce_mapping({"target_fqn": "c.s.t", "mode": "sideways"})


@pytest.mark.parametrize("fqn", ["c.s", "justone", "a.b.c.d", ""])
def test_coerce_rejects_non_three_part_target(fqn: str) -> None:
    with pytest.raises(ValidationError, match="catalog.schema.table"):
        _coerce_mapping({"target_fqn": fqn, "mode": "full"})


def test_coerce_incremental_requires_high_water_col() -> None:
    with pytest.raises(ValidationError, match="requires 'high_water_col'"):
        _coerce_mapping({"target_fqn": "c.s.t", "mode": "incremental"})


# --- _wrap_with_high_water ------------------------------------------------


def test_wrap_none_value_is_full_snapshot() -> None:
    assert (
        _wrap_with_high_water(_SPEC, "ts", None)
        == "SELECT * FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src"
    )


def test_wrap_with_value_adds_where_clause() -> None:
    assert _wrap_with_high_water(_SPEC, "ts", "2024-01-01") == (
        "SELECT * FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src WHERE \"ts\" > '2024-01-01'"
    )


def test_wrap_quotes_identifier_and_value() -> None:
    sql = _wrap_with_high_water(_SPEC, 'we"ird', "a'b")
    assert '"we""ird"' in sql
    assert "'a''b'" in sql


# --- _max_high_water_sql --------------------------------------------------


def test_max_high_water_no_value_has_no_where() -> None:
    assert _max_high_water_sql(_SPEC, "ts", None) == (
        "SELECT MAX(\"ts\") FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src"
    )


def test_max_high_water_with_value_filters() -> None:
    assert _max_high_water_sql(_SPEC, "ts", "5") == (
        "SELECT MAX(\"ts\") FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src WHERE \"ts\" > '5'"
    )


# --- load_mappings / dump_mappings ----------------------------------------


def test_load_mappings_empty_is_empty_list() -> None:
    assert load_mappings("") == []


def test_load_mappings_bad_json_is_empty_list() -> None:
    assert load_mappings("{not json") == []


def test_load_mappings_non_list_is_empty_list() -> None:
    assert load_mappings('{"a": 1}') == []


def test_load_mappings_filters_non_dict_items() -> None:
    assert load_mappings('[{"a": 1}, 7, "x", {"b": 2}]') == [{"a": 1}, {"b": 2}]


def test_dump_then_load_round_trips() -> None:
    mappings: list[dict[str, Any]] = [{"source_table": "s", "target_fqn": "c.s.t"}]
    assert load_mappings(dump_mappings(mappings)) == mappings
