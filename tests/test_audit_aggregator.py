"""Tests for the audit aggregator service + cockpit endpoints.

The service layer (:mod:`pointlessql.services.audit_aggregator`) is
covered with seeded fixtures; the route layer
(:mod:`pointlessql.api.audit_routes`) is exercised through the
ASGI test client to assert the admin gate, the parameter
validation, and the audit-of-audit ``query_history`` row that
every cockpit call must leave behind.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunToolCall,
    LineageRowReject,
    LineageValueChange,
    QueryHistory,
    UnattributedWrite,
)
from pointlessql.services import audit_aggregator as agg


@pytest.fixture
def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _seed_runs(
    now: datetime.datetime,
    *,
    count: int,
    principal: str = "alice@example.com",
) -> list[str]:
    """Insert ``count`` runs spaced one day apart, return their IDs."""
    factory = app.state.session_factory
    ids: list[str] = []
    with factory() as s:
        for i in range(count):
            run_id = str(uuid.uuid4())
            ids.append(run_id)
            s.add(
                AgentRun(
                    id=run_id,
                    principal=principal,
                    agent_id="etl",
                    notebook_path=f"nb_{i}.py",
                    status="succeeded",
                    started_at=now - datetime.timedelta(days=i),
                    finished_at=now,
                )
            )
        s.commit()
    return ids


def _seed_op(
    run_id: str,
    *,
    target: str = "cat.sch.t",
    rows_affected: int = 10,
    op_name: str = "merge",
    started_at: datetime.datetime | None = None,
    error_message: str | None = None,
) -> int:
    factory = app.state.session_factory
    with factory() as s:
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name=op_name,
            params_json="{}",
            target_table=target,
            rows_affected=rows_affected,
            started_at=started_at or datetime.datetime.now(datetime.UTC),
            finished_at=datetime.datetime.now(datetime.UTC),
            error_message=error_message,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        return op.id


# ---------------------------------------------------------------------
# service-level
# ---------------------------------------------------------------------


def test_summary_empty_db_returns_zero_for_every_metric() -> None:
    factory = app.state.session_factory
    counts = agg.summary(factory)
    assert set(counts.keys()) == agg.VALID_METRICS
    assert all(v == 0 for v in counts.values())


def test_summary_counts_runs_ops_rejects_value_changes(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    run_ids = _seed_runs(now, count=3)
    op_ids = [_seed_op(rid, rows_affected=5, started_at=now) for rid in run_ids]
    with factory() as s:
        for rid, oid in zip(run_ids, op_ids, strict=True):
            for j in range(2):
                s.add(
                    LineageRowReject(
                        run_id=rid,
                        op_id=oid,
                        source_table="cat.sch.bronze",
                        source_row_id=f"r{j}",
                        reason="on_key_null",
                        created_at=now,
                    )
                )
            s.add(
                LineageValueChange(
                    run_id=rid,
                    op_id=oid,
                    target_table="cat.sch.t",
                    target_row_id="t0",
                    target_column="email",
                    old_value="a@example.com",
                    new_value="b@example.com",
                    created_at=now,
                )
            )
        s.commit()

    counts = agg.summary(factory)
    assert counts["runs"] == 3
    assert counts["ops"] == 3
    assert counts["rejects"] == 6
    assert counts["value_changes"] == 3
    assert counts["rows_written"] == 15  # 3 ops × 5 rows


def test_summary_principal_filter_isolates_alice_from_bob(now: datetime.datetime) -> None:
    _seed_runs(now, count=2, principal="alice@example.com")
    _seed_runs(now, count=3, principal="bob@example.com")
    factory = app.state.session_factory
    assert agg.summary(factory, principal="alice@example.com")["runs"] == 2
    assert agg.summary(factory, principal="bob@example.com")["runs"] == 3
    assert agg.summary(factory, principal="nobody@example.com")["runs"] == 0


def test_summary_external_writes_count(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    with factory() as s:
        s.add(
            UnattributedWrite(
                table_fqn="cat.sch.foreign",
                delta_version=42,
                detected_at=now,
            )
        )
        s.commit()
    assert agg.summary(factory)["external_writes"] == 1


def test_summary_external_writes_with_principal_filter_returns_zero(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    with factory() as s:
        s.add(
            UnattributedWrite(
                table_fqn="cat.sch.foreign",
                delta_version=42,
                detected_at=now,
            )
        )
        s.commit()
    # External writes have no run linkage; principal filter must
    # zero them out (clean empty result, not a SQL error).
    assert agg.summary(factory, principal="anyone")["external_writes"] == 0


def test_summary_cost_denials(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    with factory() as s:
        s.add(
            AgentRun(
                id=run_id,
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="x.py",
                status="denied",
                cost_gate_trigger='{"threshold_rows": 1000000}',
                started_at=now,
            )
        )
        s.commit()
    assert agg.summary(factory)["cost_denials"] == 1
    assert agg.summary(factory)["runs"] == 1


def test_summary_tool_calls_count(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    run_ids = _seed_runs(now, count=1)
    with factory() as s:
        s.add(
            AgentRunToolCall(
                agent_run_id=run_ids[0],
                tool_name="pql_list_schemas",
                args_json="{}",
                called_at=now,
            )
        )
        s.commit()
    assert agg.summary(factory)["tool_calls"] == 1


def test_timeseries_buckets_by_day(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    _seed_runs(now, count=4)  # one run per day for 4 days
    series = agg.timeseries(factory, metric="runs", bin_="day")
    assert series["metric"] == "runs"
    assert series["bin"] == "day"
    assert series["group_by"] == "none"
    # Four distinct days, one run each.
    assert len(series["points"]) == 4
    assert all(p["value"] == 1 for p in series["points"])
    # Sorted chronologically.
    timestamps = [p["ts"] for p in series["points"]]
    assert timestamps == sorted(timestamps)


def test_timeseries_group_by_principal(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    _seed_runs(now, count=2, principal="alice@example.com")
    _seed_runs(now, count=2, principal="bob@example.com")
    series = agg.timeseries(factory, metric="runs", bin_="day", group_by="principal")
    assert series["group_by"] == "principal"
    principals = sorted({p["group"] for p in series["points"]})
    assert principals == ["alice@example.com", "bob@example.com"]


def test_anomaly_synthetic_spike_is_flagged_critical(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    # Seed three calm days, one spike day.  The spike must produce
    # `critical` because mean=0 std=0 → "any non-zero observation
    # against a zero baseline" classifies as critical.
    run_ids = _seed_runs(now, count=4)
    op_ids = [
        _seed_op(rid, started_at=now - datetime.timedelta(days=i)) for i, rid in enumerate(run_ids)
    ]
    with factory() as s:
        # 50 rejects on the most recent day (i=0 in _seed_runs is "today").
        for j in range(50):
            s.add(
                LineageRowReject(
                    run_id=run_ids[0],
                    op_id=op_ids[0],
                    source_table="cat.sch.bronze",
                    source_row_id=f"spike{j}",
                    reason="on_key_null",
                    created_at=now,
                )
            )
        s.commit()
    result = agg.anomalies(factory, metric="rejects", window_days=3, sigma=2.0, bin_="day")
    assert result["points"]
    spike = max(result["points"], key=lambda p: p["observed"])
    assert spike["observed"] == 50
    assert spike["severity"] == "critical"


def test_anomaly_steady_state_is_ok(now: datetime.datetime) -> None:
    factory = app.state.session_factory
    run_ids = _seed_runs(now, count=10)
    op_ids = [
        _seed_op(rid, started_at=now - datetime.timedelta(days=i)) for i, rid in enumerate(run_ids)
    ]
    with factory() as s:
        for rid, oid, i in zip(run_ids, op_ids, range(10), strict=True):
            for j in range(5):  # constant 5 rejects/day
                s.add(
                    LineageRowReject(
                        run_id=rid,
                        op_id=oid,
                        source_table="cat.sch.bronze",
                        source_row_id=f"r{i}_{j}",
                        reason="on_key_null",
                        created_at=now - datetime.timedelta(days=i),
                    )
                )
        s.commit()
    result = agg.anomalies(factory, metric="rejects", window_days=3, sigma=2.0, bin_="day")
    severities = {p["severity"] for p in result["points"][1:]}  # skip first point (no baseline)
    assert "critical" not in severities


# ---------------------------------------------------------------------
# route-level — admin gate, validation, self-tracking
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_route_admin_only(non_admin_client: httpx.AsyncClient) -> None:
    r = await non_admin_client.get("/api/audit/summary")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_summary_route_returns_counts(
    now: datetime.datetime, admin_client: httpx.AsyncClient
) -> None:
    _seed_runs(now, count=2)
    r = await admin_client.get("/api/audit/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"]["runs"] == 2
    assert "ops" in body["counts"]


@pytest.mark.asyncio
async def test_summary_route_records_self_in_query_history(
    now: datetime.datetime, admin_client: httpx.AsyncClient
) -> None:
    factory = app.state.session_factory
    r = await admin_client.get("/api/audit/summary")
    assert r.status_code == 200
    with factory() as s:
        rows = list(s.scalars(select(QueryHistory).where(QueryHistory.read_kind == "audit_api")))
    assert len(rows) >= 1
    assert rows[-1].sql_text.startswith("-- audit_api: /api/audit/summary")


@pytest.mark.asyncio
async def test_timeseries_route_validation(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.get("/api/audit/timeseries", params={"metric": "garbage"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_timeseries_route_returns_points(
    now: datetime.datetime, admin_client: httpx.AsyncClient
) -> None:
    _seed_runs(now, count=3)
    r = await admin_client.get(
        "/api/audit/timeseries",
        params={"metric": "runs", "bin": "day"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metric"] == "runs"
    assert len(body["points"]) == 3


@pytest.mark.asyncio
async def test_anomalies_route_returns_severity_field(
    now: datetime.datetime, admin_client: httpx.AsyncClient
) -> None:
    _seed_runs(now, count=2)
    r = await admin_client.get(
        "/api/audit/anomalies",
        params={"metric": "runs", "window_days": 3, "sigma": 2.0, "bin": "day"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["threshold_sigma"] == 2.0
    for point in body["points"]:
        assert point["severity"] in ("ok", "warn", "critical")


@pytest.mark.asyncio
async def test_summary_route_iso8601_validation(admin_client: httpx.AsyncClient) -> None:
    r = await admin_client.get("/api/audit/summary", params={"since": "garbage"})
    assert r.status_code == 422
