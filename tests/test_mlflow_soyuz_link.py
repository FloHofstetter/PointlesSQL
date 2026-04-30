"""Tests for the soyuz model-version link helpers (Phase 21.2).

Pure-function tests: ``_serialize_link`` round-trips through
``parse_link_marker``; ``build_mlflow_linked_event`` produces a
CloudEvents-1.0 envelope with the expected fields. The HTTP-level
``link_model_version_to_run`` is exercised in the manual e2e flow
because it requires a live soyuz instance.
"""

from __future__ import annotations

import json

from pointlessql.services.agent_runs.mlflow_soyuz_link import (
    EVENT_TYPE_MLFLOW_LINKED,
    _serialize_link,
    build_mlflow_linked_event,
    parse_link_marker,
)


def test_serialize_link_with_no_existing_comment() -> None:
    """Fresh comment is just the marker JSON object."""
    payload = _serialize_link(
        agent_run_id="run-123",
        mlflow_run_id="mlflow-abc",
        mlflow_experiment_id="42",
        existing_comment=None,
    )
    parsed = json.loads(payload)
    marker = parsed["_pql_link"]
    assert marker["agent_run_id"] == "run-123"
    assert marker["mlflow_run_id"] == "mlflow-abc"
    assert marker["mlflow_experiment_id"] == "42"
    assert "linked_at" in marker


def test_serialize_link_preserves_user_prose() -> None:
    """User-written comment text survives in front of the marker."""
    payload = _serialize_link(
        agent_run_id="r1",
        mlflow_run_id="m1",
        mlflow_experiment_id=None,
        existing_comment="Champion model trained on 2026-Q1 data",
    )
    chunks = payload.split("\n\n")
    assert chunks[0] == "Champion model trained on 2026-Q1 data"
    assert "_pql_link" in chunks[-1]


def test_serialize_link_replaces_old_marker_idempotently() -> None:
    """Re-linking replaces the previous marker, leaves prose alone."""
    first = _serialize_link(
        agent_run_id="r1",
        mlflow_run_id="m1",
        mlflow_experiment_id=None,
        existing_comment="Initial commentary",
    )
    second = _serialize_link(
        agent_run_id="r2",
        mlflow_run_id="m2",
        mlflow_experiment_id=None,
        existing_comment=first,
    )
    # Only one marker should remain, and it should have the new run-id.
    assert second.count("_pql_link") == 1
    parsed_marker = parse_link_marker(second)
    assert parsed_marker is not None
    assert parsed_marker["agent_run_id"] == "r2"
    assert parsed_marker["mlflow_run_id"] == "m2"
    # Prose preserved.
    assert "Initial commentary" in second


def test_parse_link_marker_returns_none_for_missing_marker() -> None:
    """Comment without the marker → None."""
    assert parse_link_marker(None) is None
    assert parse_link_marker("") is None
    assert parse_link_marker("just user text") is None


def test_parse_link_marker_extracts_payload() -> None:
    """Marker JSON in any chunk gets parsed back to a dict."""
    payload = _serialize_link(
        agent_run_id="r1",
        mlflow_run_id="m1",
        mlflow_experiment_id="exp-1",
        existing_comment="some prose",
    )
    marker = parse_link_marker(payload)
    assert marker is not None
    assert marker["agent_run_id"] == "r1"
    assert marker["mlflow_run_id"] == "m1"
    assert marker["mlflow_experiment_id"] == "exp-1"


def test_build_mlflow_linked_event_shape() -> None:
    """CloudEvents-1.0 envelope carries all link metadata."""
    envelope = build_mlflow_linked_event(
        agent_run_id="run-xyz",
        mlflow_run_id="mlflow-abc",
        model_full_name="cat.sch.m",
        model_version=3,
        mlflow_experiment_id="exp-42",
    )
    assert envelope["specversion"] == "1.0"
    assert envelope["type"] == EVENT_TYPE_MLFLOW_LINKED
    assert envelope["source"] == "/pointlessql/agent_runs/run-xyz"
    assert envelope["subject"] == "cat.sch.m@v3"
    assert envelope["datacontenttype"] == "application/json"
    data = envelope["data"]
    assert data["agent_run_id"] == "run-xyz"
    assert data["mlflow_run_id"] == "mlflow-abc"
    assert data["model_full_name"] == "cat.sch.m"
    assert data["model_version"] == 3
    assert data["mlflow_experiment_id"] == "exp-42"


def test_build_mlflow_linked_event_omits_experiment_when_none() -> None:
    """``mlflow_experiment_id=None`` → field absent from data block."""
    envelope = build_mlflow_linked_event(
        agent_run_id="run-1",
        mlflow_run_id="m-1",
        model_full_name="c.s.m",
        model_version=1,
    )
    assert "mlflow_experiment_id" not in envelope["data"]
