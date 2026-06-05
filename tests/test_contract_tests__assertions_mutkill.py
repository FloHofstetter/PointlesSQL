"""Mutation-killing tests for the contract-test assertion evaluators.

These tests pin the observable outputs of each declarative assertion
asserter in ``_assertions.py``: exact ``observation`` dict keys and
values, raised ``ValueError`` messages, default-value handling, and the
inclusive/exclusive boundaries of the numeric range comparisons.  Small
mutations to dict keys, error strings, defaults, and ``<=``/``<``
operators therefore become observable failures.
"""

from __future__ import annotations

import datetime

import pyarrow as pa
import pytest

from pointlessql.services.contract_tests import evaluate_assertion
from pointlessql.services.contract_tests._assertions import _parse_iso8601


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _table(**columns: list) -> pa.Table:
    return pa.table(columns)


# ---------------------------------------------------------------------------
# _decode_spec
# ---------------------------------------------------------------------------


def test_decode_spec_invalid_json_message() -> None:
    # A non-JSON string raises with the "spec is not valid JSON" message;
    # a ValueError(None) mutant would carry no message text.
    with pytest.raises(ValueError, match="spec is not valid JSON"):
        evaluate_assertion(
            assertion_kind="row_count_range",
            spec_json="{not json",
            table=_table(x=[1]),
        )


def test_decode_spec_non_object_json_message() -> None:
    # A JSON array decodes fine but is not a dict; the asserter rejects it
    # with the exact "must be a JSON object" message.
    with pytest.raises(ValueError, match="assertion spec must be a JSON object"):
        evaluate_assertion(
            assertion_kind="row_count_range",
            spec_json="[1, 2, 3]",
            table=_table(x=[1]),
        )


# ---------------------------------------------------------------------------
# _assert_row_count_range
# ---------------------------------------------------------------------------


def test_row_count_range_upper_bound_is_inclusive() -> None:
    # observed == max must PASS (the bound is inclusive).  A ``< hi``
    # mutant would report fail at the boundary.
    verdict = evaluate_assertion(
        assertion_kind="row_count_range",
        spec_json={"min": 0, "max": 3},
        table=_table(x=[1, 2, 3]),
    )
    assert verdict.status == "pass"
    assert verdict.observation == {"observed": 3, "min": 0, "max": 3}


# ---------------------------------------------------------------------------
# _assert_column_present
# ---------------------------------------------------------------------------


def test_column_present_requires_columns_message() -> None:
    with pytest.raises(ValueError, match="column_present requires 'columns' list"):
        evaluate_assertion(
            assertion_kind="column_present",
            spec_json={"columns": []},
            table=_table(x=[1]),
        )


def test_column_present_observation_keys() -> None:
    verdict = evaluate_assertion(
        assertion_kind="column_present",
        spec_json={"columns": ["a", "missing"]},
        table=_table(a=[1]),
    )
    assert verdict.status == "fail"
    # exact key set + values pin the "required"/"missing" key names.
    assert verdict.observation == {"required": ["a", "missing"], "missing": ["missing"]}


# ---------------------------------------------------------------------------
# _assert_value_distribution
# ---------------------------------------------------------------------------


def test_value_distribution_requires_column_message() -> None:
    # Empty column raises the exact message; a ValueError(None) or a
    # mangled-string mutant would not match.
    with pytest.raises(ValueError, match="value_distribution requires 'column'"):
        evaluate_assertion(
            assertion_kind="value_distribution",
            spec_json={"column": ""},
            table=_table(x=[1]),
        )


def test_value_distribution_empty_column_distinct_is_zero() -> None:
    # An empty (but present) column has 0 distinct values; the ``or 0``
    # fallback must keep it at 0, not bump to 1.  With max_distinct 0 the
    # 0-distinct table passes; a ``or 1`` mutant would report 1 and fail.
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "x", "min_distinct": 0, "max_distinct": 0},
        table=_table(x=pa.array([], type=pa.int64())),
    )
    assert verdict.status == "pass"
    assert verdict.observation["distinct_count"] == 0


def test_value_distribution_reads_min_distinct_key() -> None:
    # min_distinct=5 with 3 distinct => below floor => fail.  A mutant that
    # reads the wrong key (or default 1/2) would treat lo as 1 and pass.
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 5, "max_distinct": 100},
        table=_table(tier=["a", "b", "c"]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["min_distinct"] == 5
    assert verdict.observation["distinct_count"] == 3


def test_value_distribution_default_min_distinct_is_one() -> None:
    # No min_distinct => default 1.  A 1-distinct table passes (1 >= 1); a
    # default of 2 would make lo=2 and fail, and a None default would crash.
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "max_distinct": 100},
        table=_table(tier=["a", "a", "a"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["min_distinct"] == 1
    assert verdict.observation["distinct_count"] == 1


def test_value_distribution_default_max_distinct_is_huge() -> None:
    # No max_distinct => default 10**12, so 150 distinct still passes.  A
    # 10*12 (=120) mutant would make 150 > 120 and fail; a None default
    # would crash on int(None).
    values = [str(i) for i in range(150)]
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 1},
        table=_table(tier=values),
    )
    assert verdict.status == "pass"
    assert verdict.observation["distinct_count"] == 150
    assert verdict.observation["max_distinct"] == 10**12


def test_value_distribution_lower_bound_is_inclusive() -> None:
    # distinct_count == min_distinct must PASS (inclusive lower bound).  A
    # ``lo < distinct_count`` mutant would fail at the boundary.
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 2, "max_distinct": 100},
        table=_table(tier=["a", "b"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["distinct_count"] == 2


def test_value_distribution_upper_bound_is_inclusive() -> None:
    # distinct_count == max_distinct must PASS (inclusive upper bound).  A
    # ``distinct_count < hi`` mutant would fail at the boundary.
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 1, "max_distinct": 2},
        table=_table(tier=["a", "b"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["distinct_count"] == 2


def test_value_distribution_observation_key_set() -> None:
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 1, "max_distinct": 10},
        table=_table(tier=["a", "b"]),
    )
    # exact key names pin column/min_distinct/max_distinct labels.
    assert set(verdict.observation) == {
        "column",
        "distinct_count",
        "min_distinct",
        "max_distinct",
    }
    assert verdict.observation["column"] == "tier"
    assert verdict.observation["min_distinct"] == 1
    assert verdict.observation["max_distinct"] == 10


# ---------------------------------------------------------------------------
# _assert_null_rate
# ---------------------------------------------------------------------------


def test_null_rate_requires_column_message() -> None:
    with pytest.raises(ValueError, match="null_rate requires 'column'"):
        evaluate_assertion(
            assertion_kind="null_rate",
            spec_json={"max_rate": 0.1},
            table=_table(x=[1]),
        )


def test_null_rate_no_nulls_is_zero_rate() -> None:
    # Zero nulls => null_count 0, observed_rate 0.0.  A ``null_count or 1``
    # mutant would force null_count to 1 and report a non-zero rate.
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.0},
        table=_table(x=[1, 2, 3, 4]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["observed_rate"] == 0.0


def test_null_rate_at_threshold_is_inclusive() -> None:
    # observed_rate == max_rate must PASS (rate <= max).  Half null on a
    # 2-row table is exactly 0.5; a ``< max_rate`` mutant would fail it.
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.5},
        table=_table(x=pa.array([1, None], type=pa.int64())),
    )
    assert verdict.status == "pass"
    assert verdict.observation["observed_rate"] == 0.5


def test_null_rate_observation_column_key() -> None:
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.0},
        table=_table(x=[1, 2]),
    )
    assert verdict.observation["column"] == "x"
    assert set(verdict.observation) == {
        "column",
        "observed_rate",
        "max_rate",
        "rows",
    }


# ---------------------------------------------------------------------------
# _assert_referential
# ---------------------------------------------------------------------------


def test_referential_requires_column_and_allowed_message() -> None:
    with pytest.raises(ValueError, match="referential requires 'column' and 'allowed_values' list"):
        evaluate_assertion(
            assertion_kind="referential",
            spec_json={"column": "tier"},
            table=_table(tier=["a"]),
        )


def test_referential_missing_column_default_is_empty_string() -> None:
    # No 'column' key => default "" => falsy => raises ValueError (config
    # error).  A None/"XXXX" default would be truthy and instead return an
    # "column '...' not in table" error verdict rather than raising.
    with pytest.raises(ValueError, match="referential requires 'column' and 'allowed_values' list"):
        evaluate_assertion(
            assertion_kind="referential",
            spec_json={"allowed_values": ["a"]},
            table=_table(tier=["a"]),
        )


def test_referential_sample_violations_capped_at_five() -> None:
    # Six violations must report exactly the first five samples.  A ``[:6]``
    # mutant would include a sixth entry.
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "tier", "allowed_values": ["a"]},
        table=_table(tier=["b", "c", "d", "e", "f", "g"]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["violation_count"] == 6
    assert verdict.observation["sample_violations"] == ["b", "c", "d", "e", "f"]


def test_referential_observation_column_key() -> None:
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "tier", "allowed_values": ["a", "b"]},
        table=_table(tier=["a", "b"]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["column"] == "tier"
    assert set(verdict.observation) == {
        "column",
        "violation_count",
        "sample_violations",
    }


# ---------------------------------------------------------------------------
# _assert_freshness
# ---------------------------------------------------------------------------


def test_freshness_requires_timestamp_column_message() -> None:
    with pytest.raises(ValueError, match="freshness requires 'timestamp_column'"):
        evaluate_assertion(
            assertion_kind="freshness",
            spec_json={},
            table=_table(ts=["x"]),
        )


def test_freshness_default_max_lag_is_sixty_minutes() -> None:
    # No max_lag_minutes => default 60.  A timestamp ~60.5 minutes old
    # exceeds 60 => fail.  A default of 61 would (wrongly) pass it.
    stale = (_now() - datetime.timedelta(minutes=60, seconds=30)).isoformat()
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts"},
        table=_table(ts=[stale]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["max_lag_minutes"] == 60.0


def test_freshness_observation_latest_key() -> None:
    latest = _now() - datetime.timedelta(minutes=5)
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts", "max_lag_minutes": 1000},
        table=_table(ts=[latest.isoformat()]),
    )
    assert verdict.status == "pass"
    # pins the "latest" key name in the observation dict.
    assert "latest" in verdict.observation
    assert set(verdict.observation) == {"latest", "lag_minutes", "max_lag_minutes"}


# ---------------------------------------------------------------------------
# _parse_iso8601
# ---------------------------------------------------------------------------


def test_parse_iso8601_naive_datetime_becomes_utc_aware() -> None:
    # A naive datetime must be tagged as UTC (aware) — not returned naive.
    naive = datetime.datetime(2020, 1, 1, 12, 0, 0)
    parsed = _parse_iso8601(naive)
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.timedelta(0)


def test_parse_iso8601_aware_datetime_preserved() -> None:
    # An aware datetime in a non-UTC zone must be returned unchanged — not
    # rewritten to UTC.  An inverted ``is not None`` guard would clobber the
    # offset to +00:00.
    aware = datetime.datetime(
        2020, 1, 1, 12, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5))
    )
    parsed = _parse_iso8601(aware)
    assert parsed is not None
    assert parsed.utcoffset() == datetime.timedelta(hours=5)


def test_parse_iso8601_naive_string_becomes_utc_aware() -> None:
    # A naive ISO string must parse to a UTC-aware moment.
    parsed = _parse_iso8601("2020-01-01T12:00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == datetime.timedelta(0)


def test_parse_iso8601_aware_string_preserved() -> None:
    # An aware ISO string keeps its original offset (not rewritten to UTC).
    parsed = _parse_iso8601("2020-01-01T12:00:00+05:00")
    assert parsed is not None
    assert parsed.utcoffset() == datetime.timedelta(hours=5)


# ---------------------------------------------------------------------------
# Exact error-message text (kills XX-wrapped string-literal mutants).
#
# pytest.raises(match=...) uses re.search, so a mutant that wraps the
# literal as "XX...XX" still *contains* the original substring and slips
# past a match= assertion.  Pinning the FULL message with str equality
# distinguishes original from the padded mutant.
# ---------------------------------------------------------------------------


def test_decode_spec_non_object_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="row_count_range",
            spec_json="[1, 2, 3]",
            table=_table(x=[1]),
        )
    assert str(exc.value) == "assertion spec must be a JSON object"


def test_column_present_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="column_present",
            spec_json={"columns": []},
            table=_table(x=[1]),
        )
    assert str(exc.value) == "column_present requires 'columns' list"


def test_value_distribution_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="value_distribution",
            spec_json={"column": ""},
            table=_table(x=[1]),
        )
    assert str(exc.value) == "value_distribution requires 'column'"


def test_null_rate_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="null_rate",
            spec_json={"max_rate": 0.1},
            table=_table(x=[1]),
        )
    assert str(exc.value) == "null_rate requires 'column'"


def test_referential_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="referential",
            spec_json={"column": "tier"},
            table=_table(tier=["a"]),
        )
    assert str(exc.value) == "referential requires 'column' and 'allowed_values' list"


def test_freshness_message_is_exact() -> None:
    with pytest.raises(ValueError) as exc:
        evaluate_assertion(
            assertion_kind="freshness",
            spec_json={},
            table=_table(ts=["x"]),
        )
    assert str(exc.value) == "freshness requires 'timestamp_column'"
