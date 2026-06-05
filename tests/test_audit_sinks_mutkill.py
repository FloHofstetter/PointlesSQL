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


# --- async network dispatchers --------------------------------------------


import httpx  # noqa: E402

from pointlessql.services.audit import sinks as _sinks_mod  # noqa: E402
from pointlessql.services.audit.sinks import (  # noqa: E402
    AuditSinkType,
    _dispatch_cloudtrail,
    _dispatch_s3,
    dispatch_one,
    dispatch_to_sinks,
)

_ENV = {"time": "2026-03-04T05:06:07+00:00", "type": "audit.write", "id": "evt9"}


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    """Records PUT/POST calls and returns a canned status (or raises)."""

    def __init__(self, status_code: int = 200, raise_exc: Exception | None = None) -> None:
        self.status_code = status_code
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, str]] = []

    async def put(self, url: str, content: Any = None, headers: Any = None) -> _Resp:
        self.calls.append(("PUT", url))
        if self.raise_exc is not None:
            raise self.raise_exc
        return _Resp(self.status_code)

    async def post(self, url: str, content: Any = None, headers: Any = None) -> _Resp:
        self.calls.append(("POST", url))
        if self.raise_exc is not None:
            raise self.raise_exc
        return _Resp(self.status_code)

    async def aclose(self) -> None:  # pragma: no cover - never closed (injected)
        return None


def _typed_sink(config: dict[str, Any], *, type_: str) -> Any:
    return SimpleNamespace(
        id=1,
        name="s",
        type=type_,
        config_json=json.dumps(config),
        event_types_json=None,
        workspace_filter=None,
    )


_S3_CFG = {
    "bucket": "b",
    "access_key_id": "AK",
    "secret_access_key": "SK",
    "region": "eu-west-1",
    "prefix": "/pre/",
}
_CT_CFG = {
    "channel_arn": "arn:x",
    "access_key_id": "AK",
    "secret_access_key": "SK",
    "region": "us-east-2",
}


async def test_s3_success_targets_virtual_host_url() -> None:
    client = _FakeClient(status_code=200)
    ok = await _dispatch_s3(_typed_sink(_S3_CFG, type_="s3"), _ENV, client=client)
    assert ok is True
    assert client.calls == [
        ("PUT", "https://b.s3.eu-west-1.amazonaws.com/pre/audit.write/2026/03/04/evt9.json")
    ]


async def test_s3_endpoint_url_override() -> None:
    client = _FakeClient(status_code=204)
    cfg = {**_S3_CFG, "endpoint_url": "http://minio:9000/"}
    ok = await _dispatch_s3(_typed_sink(cfg, type_="s3"), _ENV, client=client)
    assert ok is True
    assert client.calls[-1][1] == "http://minio:9000/b/pre/audit.write/2026/03/04/evt9.json"


async def test_s3_missing_credentials_returns_false_without_request() -> None:
    client = _FakeClient()
    ok = await _dispatch_s3(_typed_sink({"bucket": "b"}, type_="s3"), _ENV, client=client)
    assert ok is False
    assert client.calls == []


async def test_s3_non_2xx_is_failure() -> None:
    client = _FakeClient(status_code=500)
    ok = await _dispatch_s3(_typed_sink(_S3_CFG, type_="s3"), _ENV, client=client)
    assert ok is False


async def test_s3_transport_error_is_failure() -> None:
    client = _FakeClient(raise_exc=httpx.ConnectError("down"))
    ok = await _dispatch_s3(_typed_sink(_S3_CFG, type_="s3"), _ENV, client=client)
    assert ok is False


async def test_cloudtrail_success_posts_to_data_endpoint() -> None:
    client = _FakeClient(status_code=200)
    ok = await _dispatch_cloudtrail(
        _typed_sink(_CT_CFG, type_="aws_cloudtrail"), _ENV, client=client
    )
    assert ok is True
    assert client.calls == [
        ("POST", "https://cloudtrail-data.us-east-2.amazonaws.com/PutAuditEvents")
    ]


async def test_cloudtrail_missing_config_returns_false() -> None:
    client = _FakeClient()
    ok = await _dispatch_cloudtrail(
        _typed_sink({"region": "us-east-1"}, type_="aws_cloudtrail"), _ENV, client=client
    )
    assert ok is False
    assert client.calls == []


async def test_dispatch_one_routes_by_type() -> None:
    client = _FakeClient(status_code=200)
    assert await dispatch_one(_typed_sink(_S3_CFG, type_=AuditSinkType.S3), _ENV, client=client)
    assert client.calls[-1][0] == "PUT"
    assert await dispatch_one(
        _typed_sink(_CT_CFG, type_=AuditSinkType.AWS_CLOUDTRAIL), _ENV, client=client
    )
    assert client.calls[-1][0] == "POST"


async def test_dispatch_one_webhook_missing_url_is_false() -> None:
    ok = await dispatch_one(_typed_sink({}, type_=AuditSinkType.WEBHOOK), _ENV)
    assert ok is False


async def test_dispatch_one_unknown_type_is_false() -> None:
    ok = await dispatch_one(_typed_sink({}, type_="carrier_pigeon"), _ENV)
    assert ok is False


async def test_dispatch_to_sinks_builds_per_sink_log(
    _seeded_sinks: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def _fake_dispatch_one(sink: Any, envelope: Any, *, client: Any = None) -> bool:
        seen.append(sink.name)
        return sink.name != "ws-scoped"  # one failure to exercise ok=False

    monkeypatch.setattr(_sinks_mod, "dispatch_one", _fake_dispatch_one)
    log = await dispatch_to_sinks(_factory(), {"type": "audit.wanted", "id": "e1"}, workspace_id=5)
    by_name = {entry["name"]: entry for entry in log}
    assert by_name["all"]["ok"] is True
    assert by_name["ws-scoped"]["ok"] is False
    assert set(seen) == {"all", "event-scoped", "ws-scoped"}
    assert all({"sink_id", "name", "type", "delivered_at", "ok"} <= entry.keys() for entry in log)


async def test_dispatch_to_sinks_swallows_dispatcher_exceptions(
    _seeded_sinks: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(sink: Any, envelope: Any, *, client: Any = None) -> bool:
        raise RuntimeError("dispatcher exploded")

    monkeypatch.setattr(_sinks_mod, "dispatch_one", _boom)
    log = await dispatch_to_sinks(_factory(), {"type": "audit.wanted", "id": "e1"}, workspace_id=5)
    # Emitter never raises; every entry is logged with ok=False.
    assert log and all(entry["ok"] is False for entry in log)


# --- _dispatch_syslog -----------------------------------------------------


import logging  # noqa: E402
import logging.handlers  # noqa: E402
import socket  # noqa: E402

from pointlessql.services.audit.sinks import _dispatch_syslog  # noqa: E402


class _FakeSyslogHandler(logging.Handler):
    instances: list[_FakeSyslogHandler] = []

    def __init__(self, *, address: Any, facility: Any, socktype: Any) -> None:
        super().__init__()
        self.address = address
        self.facility = facility
        self.socktype = socktype
        self.messages: list[str] = []
        _FakeSyslogHandler.instances.append(self)

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def _fake_syslog(monkeypatch: pytest.MonkeyPatch) -> Any:
    _FakeSyslogHandler.instances.clear()
    monkeypatch.setattr(logging.handlers, "SysLogHandler", _FakeSyslogHandler)
    return _FakeSyslogHandler


def test_syslog_bad_config_returns_false() -> None:
    assert _dispatch_syslog(_sink(config_json="{bad"), {"a": 1}) is False


def test_syslog_address_without_colon_returns_false() -> None:
    assert _dispatch_syslog(_sink(config_json='{"address": "nohost"}'), {"a": 1}) is False


def test_syslog_non_int_port_returns_false() -> None:
    assert _dispatch_syslog(_sink(config_json='{"address": "h:abc"}'), {"a": 1}) is False


def test_syslog_udp_default_emits_sorted_json(_fake_syslog: Any) -> None:
    ok = _dispatch_syslog(_sink(config_json='{"address": "loghost:514"}'), {"b": 2, "a": 1})
    assert ok is True
    h = _fake_syslog.instances[-1]
    assert h.address == ("loghost", 514)
    assert h.socktype == socket.SOCK_DGRAM  # udp default
    assert h.facility == 1  # default
    assert h.messages == ['{"a":1,"b":2}']


def test_syslog_tcp_uses_stream_socket(_fake_syslog: Any) -> None:
    ok = _dispatch_syslog(
        _sink(config_json='{"address": "h:601", "protocol": "tcp", "facility": 3}'), {"a": 1}
    )
    assert ok is True
    h = _fake_syslog.instances[-1]
    assert h.socktype == socket.SOCK_STREAM
    assert h.facility == 3


def test_syslog_handler_oserror_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: Any) -> Any:
        raise OSError("no socket")

    monkeypatch.setattr(logging.handlers, "SysLogHandler", _boom)
    assert _dispatch_syslog(_sink(config_json='{"address": "h:514"}'), {"a": 1}) is False
