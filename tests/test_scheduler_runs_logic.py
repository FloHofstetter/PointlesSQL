"""Mutation-killing tests for the scheduled-run pure logic.

Covers config decoding, retry arithmetic, the DAG-walk decisions
(upstream-failure detection, skip/fail message composition, run-status
roll-up), the tz normaliser + duration math, and the failure-webhook
gate + payload — every I/O-free decision the run orchestrators and the
telemetry path delegate to
:mod:`pointlessql.services.scheduler.runs._logic`.
"""

from __future__ import annotations

import datetime

import pytest

from pointlessql.services.scheduler.runs._logic import (
    build_failure_webhook_payload,
    compose_task_fail_message,
    dag_run_status,
    detect_upstream_failures,
    duration_seconds,
    ensure_utc,
    parse_config_json,
    retry_delay_seconds,
    select_max_attempts,
    should_emit_failure_webhook,
    upstream_skip_messages,
)

# --- parse_config_json ----------------------------------------------------


def test_parse_config_json_valid_dict() -> None:
    assert parse_config_json('{"a": 1}') == ({"a": 1}, None)


@pytest.mark.parametrize("raw", [None, "", "{}"])
def test_parse_config_json_empty_inputs_are_empty_dict(raw: str | None) -> None:
    assert parse_config_json(raw) == ({}, None)


def test_parse_config_json_invalid_returns_error() -> None:
    value, err = parse_config_json("{not json")
    assert value is None
    assert err is not None and err != ""


def test_parse_config_json_json_null_is_success() -> None:
    # "null" is valid JSON; the caller keys off the error slot, not value.
    assert parse_config_json("null") == (None, None)


# --- select_max_attempts --------------------------------------------------


@pytest.mark.parametrize(
    "max_retries,expected",
    [(0, 1), (1, 2), (2, 3), (-1, 1), (-5, 1)],
)
def test_select_max_attempts(max_retries: int, expected: int) -> None:
    assert select_max_attempts(max_retries) == expected


# --- retry_delay_seconds --------------------------------------------------


@pytest.mark.parametrize(
    "attempt,backoff,expected",
    [(1, 2.0, 2.0), (3, 1.5, 4.5), (2, 0.0, 0.0)],
)
def test_retry_delay_seconds(attempt: int, backoff: float, expected: float) -> None:
    out = retry_delay_seconds(attempt, backoff)
    assert out == expected
    assert isinstance(out, float)


# --- detect_upstream_failures ---------------------------------------------


def test_detect_upstream_failures_picks_failed_and_skipped() -> None:
    results = {1: "succeeded", 2: "failed", 3: "skipped"}
    assert detect_upstream_failures([1, 2, 3], results) == [2, 3]


def test_detect_upstream_failures_ignores_running_and_succeeded() -> None:
    assert detect_upstream_failures([1, 2], {1: "succeeded", 2: "running"}) == []


def test_detect_upstream_failures_unknown_dep_is_not_blocking() -> None:
    assert detect_upstream_failures([9], {}) == []


def test_detect_upstream_failures_preserves_dep_order() -> None:
    results = {1: "failed", 3: "skipped"}
    assert detect_upstream_failures([3, 1], results) == [3, 1]


# --- upstream_skip_messages -----------------------------------------------


def test_upstream_skip_messages_pair() -> None:
    detail, error = upstream_skip_messages("etl", [1, 2])
    assert detail == "task 'etl' skipped: upstream [1, 2] did not succeed"
    assert error == "upstream [1, 2] failed"


# --- compose_task_fail_message --------------------------------------------


def test_compose_task_fail_message_with_error() -> None:
    assert compose_task_fail_message("etl", "boom") == "task 'etl' failed: boom"


@pytest.mark.parametrize("err", [None, ""])
def test_compose_task_fail_message_without_error(err: str | None) -> None:
    assert compose_task_fail_message("etl", err) == "task 'etl' failed"


# --- dag_run_status -------------------------------------------------------


def test_dag_run_status_ok_drops_error() -> None:
    assert dag_run_status(True, "ignored") == ("succeeded", None)


def test_dag_run_status_failure_keeps_error() -> None:
    assert dag_run_status(False, "boom") == ("failed", "boom")


def test_dag_run_status_failure_without_error() -> None:
    assert dag_run_status(False, None) == ("failed", None)


# --- ensure_utc -----------------------------------------------------------


def test_ensure_utc_attaches_utc_to_naive() -> None:
    naive = datetime.datetime(2026, 1, 1, 12, 0, 0)
    out = ensure_utc(naive)
    assert out.tzinfo is datetime.UTC
    assert out.replace(tzinfo=None) == naive


def test_ensure_utc_leaves_aware_untouched() -> None:
    aware = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    assert ensure_utc(aware) is aware


def test_ensure_utc_does_not_convert_other_zones() -> None:
    plus_two = datetime.timezone(datetime.timedelta(hours=2))
    dt = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=plus_two)
    # An already-aware non-UTC time is returned unchanged (not shifted).
    assert ensure_utc(dt) is dt


# --- duration_seconds -----------------------------------------------------


def test_duration_seconds_positive() -> None:
    start = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    end = datetime.datetime(2026, 1, 1, 12, 0, 5, tzinfo=datetime.UTC)
    assert duration_seconds(start, end) == 5.0


def test_duration_seconds_zero_for_same_instant() -> None:
    t = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    assert duration_seconds(t, t) == 0.0


def test_duration_seconds_normalises_naive_inputs() -> None:
    start = datetime.datetime(2026, 1, 1, 12, 0, 0)  # naive
    end = datetime.datetime(2026, 1, 1, 12, 0, 10, tzinfo=datetime.UTC)
    assert duration_seconds(start, end) == 10.0


# --- should_emit_failure_webhook ------------------------------------------


def test_should_emit_failure_webhook_true_only_on_failed_with_url() -> None:
    assert should_emit_failure_webhook("failed", "https://hook") is True


@pytest.mark.parametrize(
    "status,url",
    [("failed", None), ("failed", ""), ("succeeded", "https://hook"), ("skipped", "https://h")],
)
def test_should_emit_failure_webhook_false_cases(status: str, url: str | None) -> None:
    assert should_emit_failure_webhook(status, url) is False


# --- build_failure_webhook_payload ----------------------------------------


def test_build_failure_webhook_payload_serialises_timestamps() -> None:
    started = datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.UTC)
    finished = datetime.datetime(2026, 1, 1, 12, 0, 5, tzinfo=datetime.UTC)
    payload = build_failure_webhook_payload(
        job_id=7,
        job_name="nightly",
        run_id=99,
        status="failed",
        error="boom",
        started_at=started,
        finished_at=finished,
    )
    assert payload == {
        "job_id": 7,
        "job_name": "nightly",
        "run_id": 99,
        "status": "failed",
        "error": "boom",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
    }


def test_build_failure_webhook_payload_none_timestamps() -> None:
    payload = build_failure_webhook_payload(
        job_id=1,
        job_name="",
        run_id=2,
        status="failed",
        error=None,
        started_at=None,
        finished_at=None,
    )
    assert payload["started_at"] is None
    assert payload["finished_at"] is None
    assert payload["error"] is None
