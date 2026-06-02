"""Unit tests for the agent-review dispatcher's pure helpers.

``build_envelope`` (CloudEvents 1.0 shape), ``_hash_url`` (stable audit
digest), and ``_decode_workspace_filter`` (fail-open routing filter). All
pure — light stubs stand in for the ORM rows.
"""

from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace
from typing import Any

from pointlessql.services.review_dispatcher import (
    _decode_workspace_filter,
    _hash_url,
    build_envelope,
)

_NOW = _dt.datetime(2026, 1, 1, 12, 0, tzinfo=_dt.UTC)


def _review() -> Any:
    return SimpleNamespace(
        id=7,
        run_id="run-1",
        created_at=_NOW,
        period_start=_NOW,
        period_end=_NOW,
        severity="warn",
        summary_md="all good",
    )


# --- build_envelope -------------------------------------------------------


def test_envelope_cloudevents_shape() -> None:
    env = build_envelope(_review(), event_id="evt-1", posted_at=_NOW)
    assert env["specversion"] == "1.0"
    assert env["id"] == "evt-1"
    assert env["type"]  # CLOUDEVENT_TYPE constant
    assert env["subject"] == "7"
    assert env["data"]["review_id"] == 7
    assert env["data"]["severity"] == "warn"


def test_envelope_auto_event_id_and_time() -> None:
    env = build_envelope(_review())
    assert env["id"]  # auto uuid4 hex
    assert len(env["id"]) == 32
    assert env["time"].startswith("2026-01-01T12:00")


# --- _hash_url ------------------------------------------------------------


def test_hash_url_is_stable_and_prefixed() -> None:
    a = _hash_url("https://hooks.example/x")
    b = _hash_url("https://hooks.example/x")
    assert a == b
    assert a.startswith("sha256:")
    assert len(a) == len("sha256:") + 64


def test_hash_url_differs_by_input() -> None:
    assert _hash_url("a") != _hash_url("b")


# --- _decode_workspace_filter ---------------------------------------------


def _dest(workspace_filter: Any) -> Any:
    return SimpleNamespace(id=1, workspace_filter=workspace_filter)


def test_filter_none_is_none() -> None:
    assert _decode_workspace_filter(_dest(None)) is None


def test_filter_valid_ints() -> None:
    assert _decode_workspace_filter(_dest("[1, 2]")) == {1, 2}


def test_filter_malformed_is_none() -> None:
    assert _decode_workspace_filter(_dest("not json")) is None


def test_filter_non_list_is_none() -> None:
    assert _decode_workspace_filter(_dest('{"a": 1}')) is None


def test_filter_skips_non_ints() -> None:
    assert _decode_workspace_filter(_dest('[1, {"x": 1}]')) == {1}


def test_filter_all_invalid_is_none() -> None:
    assert _decode_workspace_filter(_dest('[{"x": 1}]')) is None
