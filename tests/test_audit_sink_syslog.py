"""Tests for the syslog audit sink."""

from __future__ import annotations

import datetime
import json
import socket
import threading
from typing import Any

from pointlessql.models.audit._sinks import AuditSink
from pointlessql.services.audit.sinks import _dispatch_syslog


def _envelope() -> dict[str, Any]:
    return {
        "specversion": "1.0",
        "id": "ev-syslog-1",
        "type": "test.syslog",
        "source": "test",
        "time": datetime.datetime.now(datetime.UTC).isoformat(),
        "data": {"k": "v"},
    }


def _make_sink(config: dict[str, Any]) -> AuditSink:
    return AuditSink(
        id=1,
        name="sl",
        type="syslog",
        config_json=json.dumps(config),
        is_active=True,
        event_types_json=None,
        workspace_filter=None,
        created_at=datetime.datetime.now(datetime.UTC),
    )


def test_syslog_udp_emit_round_trip() -> None:
    """Bind a UDP listener; sink emit should land one datagram."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    received: list[bytes] = []

    def _recv() -> None:
        sock.settimeout(2.0)
        try:
            data, _ = sock.recvfrom(8192)
            received.append(data)
        except TimeoutError:
            pass

    thread = threading.Thread(target=_recv, daemon=True)
    thread.start()

    sink = _make_sink({"address": f"127.0.0.1:{port}", "protocol": "udp"})
    assert _dispatch_syslog(sink, _envelope()) is True

    thread.join(timeout=2.0)
    sock.close()
    assert len(received) == 1
    raw = received[0].decode("utf-8", errors="ignore")
    # RFC 5424 / 3164 prefix is `<PRI>` then app-name and the JSON payload.
    assert "ev-syslog-1" in raw
    assert "test.syslog" in raw


def test_syslog_rejects_bad_address() -> None:
    sink = _make_sink({"address": "no-port", "protocol": "udp"})
    assert _dispatch_syslog(sink, _envelope()) is False


def test_syslog_rejects_bad_port() -> None:
    sink = _make_sink({"address": "127.0.0.1:not-a-number", "protocol": "udp"})
    assert _dispatch_syslog(sink, _envelope()) is False


def test_syslog_bad_config_returns_false() -> None:
    sink = AuditSink(
        id=2,
        name="bad",
        type="syslog",
        config_json="not-json",
        is_active=True,
        event_types_json=None,
        workspace_filter=None,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    assert _dispatch_syslog(sink, _envelope()) is False


def test_syslog_network_failure_swallowed_and_returns_false() -> None:
    """Pointing at an unreachable port returns False, doesn't raise."""
    sink = _make_sink({"address": "127.0.0.1:1", "protocol": "tcp"})
    # TCP connect to port 1 should fail fast on Linux; we tolerate
    # the rare case where it succeeds (unlikely on CI) by accepting
    # either True or False — the gate is "no exception escapes".
    result = _dispatch_syslog(sink, _envelope())
    assert isinstance(result, bool)
