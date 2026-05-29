"""Contract-test assertion evaluators (Phase 142)."""

from __future__ import annotations

import datetime

import pyarrow as pa
import pytest

from pointlessql.services.contract_tests import evaluate_assertion


def _table(**columns: list) -> pa.Table:
    return pa.table(columns)


def test_row_count_range_pass() -> None:
    verdict = evaluate_assertion(
        assertion_kind="row_count_range",
        spec_json={"min": 1, "max": 100},
        table=_table(x=[1, 2, 3]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["observed"] == 3


def test_row_count_range_fail_above_max() -> None:
    verdict = evaluate_assertion(
        assertion_kind="row_count_range",
        spec_json={"min": 1, "max": 2},
        table=_table(x=[1, 2, 3]),
    )
    assert verdict.status == "fail"


def test_column_present_pass() -> None:
    verdict = evaluate_assertion(
        assertion_kind="column_present",
        spec_json={"columns": ["id", "name"]},
        table=_table(id=[1], name=["a"], extra=["x"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["missing"] == []


def test_column_present_fail_with_missing() -> None:
    verdict = evaluate_assertion(
        assertion_kind="column_present",
        spec_json={"columns": ["id", "missing"]},
        table=_table(id=[1]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["missing"] == ["missing"]


def test_column_present_requires_columns_list() -> None:
    with pytest.raises(ValueError, match="columns"):
        evaluate_assertion(
            assertion_kind="column_present",
            spec_json={},
            table=_table(id=[1]),
        )


def test_value_distribution_pass() -> None:
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 2, "max_distinct": 5},
        table=_table(tier=["a", "b", "a", "c"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["distinct_count"] == 3


def test_value_distribution_missing_column_errors() -> None:
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "missing"},
        table=_table(tier=["a"]),
    )
    assert verdict.status == "error"


def test_null_rate_pass() -> None:
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.5},
        table=_table(x=[1, 2, None, 4]),
    )
    assert verdict.status == "pass"
    assert pytest.approx(verdict.observation["observed_rate"], rel=0.01) == 0.25


def test_null_rate_fail() -> None:
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.0},
        table=_table(x=[None, None]),
    )
    assert verdict.status == "fail"


def test_referential_pass() -> None:
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "tier", "allowed_values": ["a", "b", "c"]},
        table=_table(tier=["a", "b", "a"]),
    )
    assert verdict.status == "pass"


def test_referential_fail_with_sample() -> None:
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "tier", "allowed_values": ["a"]},
        table=_table(tier=["a", "b", "c", "d"]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["violation_count"] == 3
    assert len(verdict.observation["sample_violations"]) <= 5


def test_freshness_pass() -> None:
    now = datetime.datetime.now(datetime.UTC)
    fresh = (now - datetime.timedelta(minutes=5)).isoformat()
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts", "max_lag_minutes": 60},
        table=_table(ts=[fresh]),
    )
    assert verdict.status == "pass"


def test_freshness_fail_too_old() -> None:
    now = datetime.datetime.now(datetime.UTC)
    stale = (now - datetime.timedelta(hours=8)).isoformat()
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts", "max_lag_minutes": 60},
        table=_table(ts=[stale]),
    )
    assert verdict.status == "fail"


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="unknown assertion"):
        evaluate_assertion(
            assertion_kind="not_a_kind",
            spec_json={},
            table=_table(x=[1]),
        )


def test_assertion_spec_must_be_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        evaluate_assertion(
            assertion_kind="row_count_range",
            spec_json="[1,2,3]",
            table=_table(x=[1]),
        )
