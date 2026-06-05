"""Mutation-killing tests for the ``alert_check`` executor's pure logic.

Covers config validation, table-reference parsing, the storage-location
guard, the data-health summary string, and the webhook-destination
filter — every I/O-free decision the executor delegates to
:mod:`pointlessql.services.scheduler.executors._alert_check_logic`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.scheduler.executors._alert_check_logic import (
    active_webhook_destinations,
    build_alert_summary_md,
    parse_table_ref,
    valid_storage_location,
    validate_alert_config,
)


def _dest(kind: str, webhook_url: str | None) -> Any:
    """Build a duck-typed stand-in for an AlertDestination row."""
    return SimpleNamespace(kind=kind, webhook_url=webhook_url)


# --- validate_alert_config ------------------------------------------------


def test_validate_alert_config_returns_int() -> None:
    assert validate_alert_config({"alert_id": 42}) == 42


@pytest.mark.parametrize("config", [{}, {"alert_id": "42"}, {"alert_id": None}, {"alert_id": 1.5}])
def test_validate_alert_config_rejects_non_int(config: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="missing integer 'alert_id'"):
        validate_alert_config(config)


# --- parse_table_ref ------------------------------------------------------


def test_parse_table_ref_three_part() -> None:
    assert parse_table_ref("cat.sch.tbl") == ("cat", "sch", "tbl")


@pytest.mark.parametrize("ref", ["justone", "a.b", "a.b.c.d", "", "a.b.c.d.e"])
def test_parse_table_ref_rejects_non_three_part(ref: str) -> None:
    assert parse_table_ref(ref) is None


# --- valid_storage_location -----------------------------------------------


def test_valid_storage_location_passes_non_empty_string() -> None:
    assert valid_storage_location("s3://bucket/path") == "s3://bucket/path"


@pytest.mark.parametrize("value", ["", None, 123, [], {"x": 1}])
def test_valid_storage_location_rejects_empty_or_non_string(value: Any) -> None:
    assert valid_storage_location(value) is None


# --- build_alert_summary_md -----------------------------------------------


def test_build_alert_summary_md_exact_string() -> None:
    assert build_alert_summary_md("rev-spike", 5, "gt", 3) == (
        "Alert 'rev-spike' fired — 5 rows gt 3"
    )


def test_build_alert_summary_md_interpolates_all_fields() -> None:
    out = build_alert_summary_md("nulls", 0, "lt", 10)
    assert "nulls" in out
    assert "0 rows" in out
    assert "lt" in out
    assert out.endswith(" 10")


# --- active_webhook_destinations ------------------------------------------


def test_active_webhook_destinations_keeps_only_deliverable() -> None:
    deliverable = _dest("webhook", "https://hook.example/a")
    dests = [
        deliverable,
        _dest("email", "https://hook.example/b"),  # wrong kind
        _dest("webhook", None),  # no url
        _dest("webhook", ""),  # empty url
    ]
    assert active_webhook_destinations(dests) == [(deliverable, "https://hook.example/a")]


def test_active_webhook_destinations_preserves_order_and_pairs_url() -> None:
    a = _dest("webhook", "https://a")
    b = _dest("webhook", "https://b")
    assert active_webhook_destinations([a, b]) == [(a, "https://a"), (b, "https://b")]


def test_active_webhook_destinations_empty() -> None:
    assert active_webhook_destinations([]) == []
