"""Correlation-ids — cross-product tracing.

Covers the data-mesh δ correlation half: the request-id middleware
echoing/propagating ``X-Correlation-ID``, the op recorder stamping it
onto ``agent_run_operations``, and the mesh trace query grouping every
operation that shares a correlation id into one timeline.
"""

from __future__ import annotations

import datetime

import httpx
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.config import Settings, correlation_id_var, request_id_var
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs.operations._lifecycle import record_operation
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client


def _factory():
    return app.state.session_factory


def _create_run(run_id: str) -> str:
    with _factory()() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal=None,
                agent_id="test-agent",
                notebook_path="demo/x.py",
                status="running",
                started_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return run_id


def _record(run_id: str, op_name: str = "write_table", target: str | None = None) -> int:
    started = datetime.datetime.now(datetime.UTC)
    return record_operation(
        _factory(),
        agent_run_id=run_id,
        op_name=op_name,
        params={"full_name": target or "main.x.y"},
        target_table=target,
        input_sha=None,
        rows_affected=1,
        delta_version_before=None,
        delta_version_after=0,
        started_at=started,
        finished_at=started + datetime.timedelta(milliseconds=1),
        error_message=None,
    )


def test_record_operation_stamps_correlation_from_contextvar() -> None:
    run_id = _create_run("cccccccc-cccc-cccc-cccc-cccccccccccc")
    token = correlation_id_var.set("corr-abc")
    try:
        op_id = _record(run_id, target="main.a.t1")
    finally:
        correlation_id_var.reset(token)
    with _factory()() as session:
        row = session.get(AgentRunOperation, op_id)
        assert row is not None
        assert row.correlation_id == "corr-abc"


def test_record_operation_no_correlation_outside_request() -> None:
    run_id = _create_run("dddddddd-dddd-dddd-dddd-dddddddddddd")
    # No correlation context set → column stays NULL.
    op_id = _record(run_id, target="main.a.t2")
    with _factory()() as session:
        assert session.get(AgentRunOperation, op_id).correlation_id is None


def test_trace_query_groups_ops_by_correlation() -> None:
    run_id = _create_run("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
    token = correlation_id_var.set("trace-xyz")
    try:
        _record(run_id, target="main.a.one")
        _record(run_id, target="main.b.two")
    finally:
        correlation_id_var.reset(token)
    with _factory()() as session:
        ops = session.scalars(
            select(AgentRunOperation).where(AgentRunOperation.correlation_id == "trace-xyz")
        ).all()
    assert len(ops) == 2


async def test_middleware_echoes_correlation_header() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/mesh/graph", headers={"X-Correlation-ID": "my-trace"})
    assert res.status_code == 200, res.text
    assert res.headers.get("X-Correlation-ID") == "my-trace"


async def test_middleware_defaults_correlation_to_request_id() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/mesh/graph")
    assert res.status_code == 200, res.text
    # No inbound correlation id → falls back to the request id.
    assert res.headers.get("X-Correlation-ID") == res.headers.get("X-Request-ID")


def test_soyuz_client_forwards_active_trace_ids() -> None:
    """The default client stamps the active request + correlation ids."""
    rt = request_id_var.set("req-123")
    ct = correlation_id_var.set("corr-abc")
    try:
        headers = make_soyuz_client(Settings()).get_httpx_client().headers
    finally:
        correlation_id_var.reset(ct)
        request_id_var.reset(rt)
    assert headers["x-request-id"] == "req-123"
    assert headers["x-correlation-id"] == "corr-abc"


def test_principal_client_forwards_trace_ids_and_keeps_principal() -> None:
    """The per-principal client carries the trace ids alongside X-Principal."""
    rt = request_id_var.set("req-9")
    ct = correlation_id_var.set("corr-9")
    try:
        headers = make_principal_client(Settings(), "user@test.com").get_httpx_client().headers
    finally:
        correlation_id_var.reset(ct)
        request_id_var.reset(rt)
    assert headers["x-principal"] == "user@test.com"
    assert headers["x-request-id"] == "req-9"
    assert headers["x-correlation-id"] == "corr-9"


def test_soyuz_client_correlation_defaults_to_request_id() -> None:
    """With no correlation set, the request id is forwarded as the correlation."""
    rt = request_id_var.set("req-only")
    try:
        headers = make_soyuz_client(Settings()).get_httpx_client().headers
    finally:
        request_id_var.reset(rt)
    assert headers["x-correlation-id"] == "req-only"


def test_soyuz_client_omits_trace_headers_outside_request() -> None:
    """Outside any request scope no trace headers are forwarded."""
    # The autouse fixtures do not set the trace context vars, but a prior
    # test could have leaked one — assert against a clean explicit reset.
    rt = request_id_var.set("")
    ct = correlation_id_var.set("")
    try:
        headers = make_soyuz_client(Settings()).get_httpx_client().headers
    finally:
        correlation_id_var.reset(ct)
        request_id_var.reset(rt)
    assert "x-request-id" not in headers
    assert "x-correlation-id" not in headers


async def test_trace_endpoint_returns_timeline() -> None:
    run_id = _create_run("ffffffff-ffff-ffff-ffff-ffffffffffff")
    token = correlation_id_var.set("api-trace")
    try:
        _record(run_id, target="main.a.alpha")
        _record(run_id, target="main.b.beta")
    finally:
        correlation_id_var.reset(token)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/mesh/trace/api-trace")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["correlation_id"] == "api-trace"
    assert len(body["operations"]) == 2
