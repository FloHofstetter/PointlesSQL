"""Unit tests for the audit-sink config/filter decoders.

``_decode_config`` / ``_decode_event_filter`` / ``_decode_workspace_filter``
read string columns off an ``AuditSink`` row and parse them defensively —
config is fail-loud (bad JSON raises), the two filters are fail-open
(malformed / empty → ``None`` = "everything"). They only touch a handful of
attributes, so a light stub stands in for the ORM row.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.services.audit.sinks import (
    _decode_config,
    _decode_event_filter,
    _decode_workspace_filter,
)


def _sink(**kw: Any) -> Any:
    base = {"id": 1, "config_json": "{}", "event_types_json": None, "workspace_filter": None}
    base.update(kw)
    return SimpleNamespace(**base)


# --- _decode_config (fail-loud) ------------------------------------------


def test_decode_config_valid_object() -> None:
    assert _decode_config(_sink(config_json='{"url": "x"}')) == {"url": "x"}


def test_decode_config_empty_is_empty_dict() -> None:
    assert _decode_config(_sink(config_json=None)) == {}


def test_decode_config_non_object_raises() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        _decode_config(_sink(config_json="[1, 2]"))


# --- _decode_event_filter (fail-open) ------------------------------------


def test_event_filter_none_is_none() -> None:
    assert _decode_event_filter(_sink(event_types_json=None)) is None


def test_event_filter_list_becomes_set() -> None:
    assert _decode_event_filter(_sink(event_types_json='["a", "b"]')) == {"a", "b"}


def test_event_filter_empty_list_is_none() -> None:
    assert _decode_event_filter(_sink(event_types_json="[]")) is None


def test_event_filter_malformed_is_none() -> None:
    assert _decode_event_filter(_sink(event_types_json="{not json")) is None


def test_event_filter_non_list_is_none() -> None:
    assert _decode_event_filter(_sink(event_types_json='{"a": 1}')) is None


# --- _decode_workspace_filter (fail-open, int-coercing) ------------------


def test_workspace_filter_none_is_none() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter=None)) is None


def test_workspace_filter_ints() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter="[1, 2, 3]")) == {1, 2, 3}


def test_workspace_filter_coerces_string_ints() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter='["4", "5"]')) == {4, 5}


def test_workspace_filter_skips_non_ints() -> None:
    # Non-coercible entries are dropped; the rest survive.
    assert _decode_workspace_filter(_sink(workspace_filter='[1, {"x": 1}]')) == {1}


def test_workspace_filter_all_invalid_is_none() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter='[{"x": 1}]')) is None


def test_workspace_filter_malformed_is_none() -> None:
    assert _decode_workspace_filter(_sink(workspace_filter="not json")) is None
