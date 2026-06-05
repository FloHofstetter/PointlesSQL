"""Mutation-killing tests for the ingest pull-mapping pure helpers.

Covers mapping validation/normalisation, the high-water incremental
SQL wrappers, and the table-mappings JSON load/dump round-trip.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest._pull_logic import (
    coerce_mapping,
    compute_new_high_water,
    max_high_water_sql,
    prepare_select_sql,
    safe_row_count,
    select_write_strategy,
    wrap_with_high_water,
)
from pointlessql.services.ingest.connectors import ReaderSpec
from pointlessql.services.ingest.pull import dump_mappings, load_mappings

_SPEC = ReaderSpec(sql="SELECT * FROM read_csv_auto('x');")


# --- coerce_mapping ------------------------------------------------------


def test_coerce_full_mode_normalises() -> None:
    out = coerce_mapping({"source_table": " s ", "target_fqn": "c.s.t", "mode": "full"})
    assert out == {
        "source_table": "s",
        "target_fqn": "c.s.t",
        "mode": "full",
        "high_water_col": None,
        "last_high_water_value": None,
    }


def test_coerce_mode_defaults_to_full() -> None:
    out = coerce_mapping({"target_fqn": "c.s.t"})
    assert out["mode"] == "full"


def test_coerce_incremental_keeps_high_water() -> None:
    out = coerce_mapping(
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
        coerce_mapping({"target_fqn": "c.s.t", "mode": "sideways"})


@pytest.mark.parametrize("fqn", ["c.s", "justone", "a.b.c.d", ""])
def test_coerce_rejects_non_three_part_target(fqn: str) -> None:
    with pytest.raises(ValidationError, match="catalog.schema.table"):
        coerce_mapping({"target_fqn": fqn, "mode": "full"})


def test_coerce_incremental_requires_high_water_col() -> None:
    with pytest.raises(ValidationError, match="requires 'high_water_col'"):
        coerce_mapping({"target_fqn": "c.s.t", "mode": "incremental"})


# --- wrap_with_high_water ------------------------------------------------


def test_wrap_none_value_is_full_snapshot() -> None:
    assert (
        wrap_with_high_water(_SPEC, "ts", None)
        == "SELECT * FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src"
    )


def test_wrap_with_value_adds_where_clause() -> None:
    assert wrap_with_high_water(_SPEC, "ts", "2024-01-01") == (
        "SELECT * FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src WHERE \"ts\" > '2024-01-01'"
    )


def test_wrap_quotes_identifier_and_value() -> None:
    sql = wrap_with_high_water(_SPEC, 'we"ird', "a'b")
    assert '"we""ird"' in sql
    assert "'a''b'" in sql


# --- max_high_water_sql --------------------------------------------------


def test_max_high_water_no_value_has_no_where() -> None:
    assert max_high_water_sql(_SPEC, "ts", None) == (
        "SELECT MAX(\"ts\") FROM (SELECT * FROM read_csv_auto('x')) AS _pql_src"
    )


def test_max_high_water_with_value_filters() -> None:
    assert max_high_water_sql(_SPEC, "ts", "5") == (
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


# --- compute_new_high_water -----------------------------------------------


def test_compute_high_water_uses_fetched_value() -> None:
    assert compute_new_high_water(("2026-02-01",), "2026-01-01") == "2026-02-01"


def test_compute_high_water_stringifies_non_string_cell() -> None:
    assert compute_new_high_water((5,), None) == "5"


def test_compute_high_water_null_cell_keeps_previous() -> None:
    # Empty post-cutoff window (NULL MAX) must not regress the watermark.
    assert compute_new_high_water((None,), "2026-01-01") == "2026-01-01"


def test_compute_high_water_null_cell_first_pull_is_none() -> None:
    assert compute_new_high_water((None,), None) is None


@pytest.mark.parametrize("row", [None, ()])
def test_compute_high_water_missing_row_keeps_previous(row: Any) -> None:
    # ``None`` (no row) and ``()`` (falsy row) both fall back to last_value.
    assert compute_new_high_water(row, "keep") == "keep"


# --- prepare_select_sql ---------------------------------------------------


def test_prepare_select_full_strips_trailing_semicolon() -> None:
    assert prepare_select_sql(_SPEC, "full", None, None) == "SELECT * FROM read_csv_auto('x')"


def test_prepare_select_incremental_first_pull_is_full_snapshot() -> None:
    sql = prepare_select_sql(_SPEC, "incremental", "ts", None)
    assert "WHERE" not in sql
    assert "_pql_src" in sql


def test_prepare_select_incremental_delta_adds_where() -> None:
    sql = prepare_select_sql(_SPEC, "incremental", "ts", "5")
    assert "WHERE \"ts\" > '5'" in sql


# --- select_write_strategy ------------------------------------------------


def test_strategy_full_overwrites() -> None:
    assert select_write_strategy("full", None, None) == ("write_table", {"mode": "overwrite"})


def test_strategy_full_ignores_watermark() -> None:
    # Even with a watermark present, full mode overwrites — never merges.
    assert select_write_strategy("full", "5", "ts") == ("write_table", {"mode": "overwrite"})


def test_strategy_incremental_first_pull_bootstraps_with_overwrite() -> None:
    assert select_write_strategy("incremental", None, "ts") == (
        "write_table",
        {"mode": "overwrite"},
    )


def test_strategy_incremental_with_watermark_merges() -> None:
    assert select_write_strategy("incremental", "5", "ts") == (
        "merge",
        {"on": ["ts"], "strategy": "upsert"},
    )


# --- safe_row_count -------------------------------------------------------


def test_safe_row_count_reads_first_shape_axis() -> None:
    assert safe_row_count(SimpleNamespace(shape=(5, 3))) == 5


def test_safe_row_count_zero_rows() -> None:
    assert safe_row_count(SimpleNamespace(shape=(0, 7))) == 0


def test_safe_row_count_missing_shape_defaults_zero() -> None:
    assert safe_row_count(object()) == 0
