"""Tests for the stdout-JSON audit sink."""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from pointlessql.models.audit._sinks import AuditSink
from pointlessql.services.audit.sinks import _dispatch_stdout_json


def _envelope() -> dict[str, Any]:
    return {
        "specversion": "1.0",
        "id": "ev-1",
        "type": "test.event",
        "source": "test",
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
        "data": {"key": "value"},
    }


def test_stdout_json_writes_single_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = AuditSink(
        id=1,
        name="test-stdout",
        type="stdout_json",
        config_json="{}",
        is_active=True,
        event_types_json=None,
        workspace_filter=None,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    assert _dispatch_stdout_json(sink, _envelope()) is True
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    line = out.strip()
    payload = json.loads(line)
    assert payload["id"] == "ev-1"
    assert payload["type"] == "test.event"


def test_stdout_json_stream_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = AuditSink(
        id=2,
        name="test-stderr",
        type="stdout_json",
        config_json=json.dumps({"stream": "stderr"}),
        is_active=True,
        event_types_json=None,
        workspace_filter=None,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    assert _dispatch_stdout_json(sink, _envelope()) is True
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert captured.out == ""


def test_stdout_json_bad_config_returns_false(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = AuditSink(
        id=3,
        name="bad",
        type="stdout_json",
        config_json="not-a-json-object",
        is_active=True,
        event_types_json=None,
        workspace_filter=None,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    assert _dispatch_stdout_json(sink, _envelope()) is False
