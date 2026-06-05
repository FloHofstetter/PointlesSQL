"""Unit tests for the ingest-pull pure helpers.

``coerce_mapping`` (mapping-shape validation), ``wrap_with_high_water`` /
``max_high_water_sql`` (incremental SQL construction), and the
``load_mappings`` / ``dump_mappings`` JSON serde. All pure — a light stub
stands in for the ReaderSpec, and the connector/DB ``pull_mapping`` path is
left to the integration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.ingest._pull_logic import (
    coerce_mapping,
    max_high_water_sql,
    wrap_with_high_water,
)
from pointlessql.services.ingest.pull import dump_mappings, load_mappings

_SPEC = SimpleNamespace(sql="SELECT * FROM t")


# --- coerce_mapping ------------------------------------------------------


def test_coerce_valid_full_mapping() -> None:
    out = coerce_mapping({"source_table": "s", "target_fqn": "c.s.t", "mode": "full"})
    assert out["mode"] == "full"
    assert out["target_fqn"] == "c.s.t"


def test_coerce_bad_mode_raises() -> None:
    with pytest.raises(ValidationError, match="Mapping mode"):
        coerce_mapping({"target_fqn": "c.s.t", "mode": "sideways"})


def test_coerce_bad_target_fqn_raises() -> None:
    with pytest.raises(ValidationError, match="target_fqn"):
        coerce_mapping({"target_fqn": "c.s", "mode": "full"})


def test_coerce_incremental_requires_high_water_col() -> None:
    with pytest.raises(ValidationError, match="high_water_col"):
        coerce_mapping({"target_fqn": "c.s.t", "mode": "incremental"})


def test_coerce_incremental_ok() -> None:
    out = coerce_mapping(
        {"target_fqn": "c.s.t", "mode": "incremental", "high_water_col": "updated_at"}
    )
    assert out["high_water_col"] == "updated_at"


# --- high-water SQL -------------------------------------------------------


def test_wrap_high_water_first_pull_is_full() -> None:
    sql = wrap_with_high_water(_SPEC, "updated_at", None)
    assert "WHERE" not in sql
    assert "_pql_src" in sql


def test_wrap_high_water_delta_adds_where() -> None:
    sql = wrap_with_high_water(_SPEC, "updated_at", "2026-01-01")
    assert "WHERE" in sql
    assert "2026-01-01" in sql


def test_max_high_water_no_filter_on_first_pull() -> None:
    sql = max_high_water_sql(_SPEC, "updated_at", None)
    assert sql.startswith("SELECT MAX(")
    assert "WHERE" not in sql


def test_max_high_water_filters_on_delta() -> None:
    sql = max_high_water_sql(_SPEC, "updated_at", "2026-01-01")
    assert "WHERE" in sql


# --- load / dump mappings -------------------------------------------------


def test_load_mappings_empty_string() -> None:
    assert load_mappings("") == []


def test_load_mappings_valid() -> None:
    assert load_mappings('[{"target_fqn": "c.s.t"}]') == [{"target_fqn": "c.s.t"}]


def test_load_mappings_malformed_is_empty() -> None:
    assert load_mappings("{not json") == []


def test_load_mappings_non_list_is_empty() -> None:
    assert load_mappings('{"a": 1}') == []


def test_load_mappings_filters_non_dicts() -> None:
    assert load_mappings('[{"a": 1}, 5, "x"]') == [{"a": 1}]


def test_dump_mappings_round_trips() -> None:
    data: list[dict[str, Any]] = [{"target_fqn": "c.s.t", "mode": "full"}]
    assert load_mappings(dump_mappings(data)) == data
