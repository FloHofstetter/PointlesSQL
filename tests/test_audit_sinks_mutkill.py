"""Mutation-killing tests for the audit-sink decode + selection helpers.

Covers the pure config/filter decoders, the synchronous stdout-JSON
dispatcher, and the active-sink selection (event-type + workspace
allow-lists).  The async network dispatchers are out of scope here.
"""

from __future__ import annotations

import datetime
import json
from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.api.main import app
from pointlessql.models import AuditSink
from pointlessql.services.audit.sinks import (
    _decode_config,
    _decode_event_filter,
    _decode_workspace_filter,
    _dispatch_stdout_json,
    _select_active_sinks,
)


def _sink(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "id": 1,
        "config_json": "{}",
        "event_types_json": None,
        "workspace_filter": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# --- _decode_config -------------------------------------------------------


def test_decode_config_parses_object() -> None:
    assert _decode_config(_sink(config_json='{"url": "x"}')) == {"url": "x"}


def test_decode_config_empty_defaults_to_empty_dict() -> None:
    assert _decode_config(_sink(config_json=None)) == {}


def test_decode_config_non_object_raises() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        _decode_config(_sink(config_json="[1, 2]"))


# --- _decode_event_filter -------------------------------------------------


def test_event_filter_none_when_absent() -> None:
    assert _decode_event_filter(_sink(event_types_json=None)) is None


def test_event_filter_none_when_empty_list() -> None:
    assert _decode_event_filter(_sink(event_types_json="[]")) is None


def test_event_filter_none_when_bad_json() -> None:
    assert _decode_event_filter(_sink(event_types_json="{not json")) is None


def test_event_filter_none_when_not_a_list() -> None:
    assert _decode_event_filter(_sink(event_types_json='{"a": 1}')) is None


def test_event_filter_returns_str_set() -> None:
    assert _decode_event_filter(_sink(event_types_json='["a", "b", 3]')) == {"a", "b", "3"}


# --- _decode_workspace_filter ---------------------------------------------


def test_workspace_filter_none_when_absent() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter=None)) is None


def test_workspace_filter_none_when_empty() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter="[]")) is None


def test_workspace_filter_none_when_bad_json() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter="oops")) is None


def test_workspace_filter_coerces_ints() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter='[1, 2, "3"]')) == {1, 2, 3}


def test_workspace_filter_skips_non_int_entries() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter='[1, "x"]')) == {1}


def test_workspace_filter_all_invalid_is_none() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter='["x", "y"]')) is None


# --- _dispatch_stdout_json ------------------------------------------------


def test_stdout_json_writes_sorted_compact_line(capsys: pytest.CaptureFixture[str]) -> None:
    ok = _dispatch_stdout_json(_sink(), {"b": 2, "a": 1})
    assert ok is True
    out = capsys.readouterr().out
    assert out == '{"a":1,"b":2}\n'


def test_stdout_json_honours_stderr_stream(capsys: pytest.CaptureFixture[str]) -> None:
    ok = _dispatch_stdout_json(_sink(config_json='{"stream": "stderr"}'), {"a": 1})
    assert ok is True
    captured = capsys.readouterr()
    assert captured.err == '{"a":1}\n'
    assert captured.out == ""


def test_stdout_json_bad_config_returns_false(capsys: pytest.CaptureFixture[str]) -> None:
    assert _dispatch_stdout_json(_sink(config_json="{bad"), {"a": 1}) is False
    assert capsys.readouterr().out == ""


# --- _select_active_sinks (DB) --------------------------------------------


def _factory() -> Any:
    return app.state.session_factory


@pytest.fixture
def _seeded_sinks() -> Any:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.query(AuditSink).delete()
        session.add_all(
            [
                AuditSink(
                    name="all",
                    type="stdout_json",
                    config_json="{}",
                    is_active=True,
                    created_at=now,
                ),
                AuditSink(
                    name="event-scoped",
                    type="stdout_json",
                    config_json="{}",
                    is_active=True,
                    event_types_json=json.dumps(["audit.wanted"]),
                    created_at=now,
                ),
                AuditSink(
                    name="ws-scoped",
                    type="stdout_json",
                    config_json="{}",
                    is_active=True,
                    workspace_filter=json.dumps([5]),
                    created_at=now,
                ),
                AuditSink(
                    name="inactive",
                    type="stdout_json",
                    config_json="{}",
                    is_active=False,
                    created_at=now,
                ),
            ]
        )
        session.commit()
    yield
    with _factory()() as session:
        session.query(AuditSink).delete()
        session.commit()


def test_select_skips_inactive_sinks(_seeded_sinks: Any) -> None:
    with _factory()() as session:
        names = {
            s.name for s in _select_active_sinks(session, event_type="audit.wanted", workspace_id=5)
        }
    assert "inactive" not in names


def test_select_event_filter_excludes_non_matching(_seeded_sinks: Any) -> None:
    with _factory()() as session:
        names = {
            s.name for s in _select_active_sinks(session, event_type="audit.other", workspace_id=5)
        }
    # event-scoped only fires for audit.wanted.
    assert names == {"all", "ws-scoped"}


def test_select_workspace_filter_excludes_non_matching(_seeded_sinks: Any) -> None:
    with _factory()() as session:
        names = {
            s.name
            for s in _select_active_sinks(session, event_type="audit.wanted", workspace_id=99)
        }
    # ws-scoped only fires for workspace 5.
    assert names == {"all", "event-scoped"}


def test_select_workspace_none_skips_workspace_filter(_seeded_sinks: Any) -> None:
    with _factory()() as session:
        names = {
            s.name
            for s in _select_active_sinks(session, event_type="audit.wanted", workspace_id=None)
        }
    # No workspace filtering -> ws-scoped passes too.
    assert names == {"all", "event-scoped", "ws-scoped"}


def test_select_returns_pk_ordered(_seeded_sinks: Any) -> None:
    with _factory()() as session:
        rows = _select_active_sinks(session, event_type="audit.wanted", workspace_id=5)
    ids = [s.id for s in rows]
    assert ids == sorted(ids)
