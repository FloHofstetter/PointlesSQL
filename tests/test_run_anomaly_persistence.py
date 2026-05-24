"""run-finish writes ``anomaly_severity`` + ``anomaly_metric``.

Round-trip verification that the finish-handler hook persists the
verdict onto the ``agent_runs`` row, that ``backfill_run_anomalies``
fills in pre-existing rows, and that the runs-list serializer
exposes the cached fields.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation, LineageRowReject
from pointlessql.services import audit_aggregator as agg


def _seed_baseline() -> None:
    """Insert a quiet baseline of one reject per day for 7 prior days."""
    factory = app.state.session_factory
    today = dt.datetime.now(dt.UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    with factory() as session:
        for offset in range(7, 0, -1):
            day = today - dt.timedelta(days=offset)
            run_id = f"baseline-{offset:02d}-{'0' * 28}"[:36]
            session.add(
                AgentRun(
                    id=run_id,
                    principal="seed@test.com",
                    agent_id="seeder",
                    notebook_path="seed.py",
                    source_snapshot_sha="0" * 64,
                    status="succeeded",
                    started_at=day,
                    finished_at=day,
                )
            )
            session.flush()
            op = AgentRunOperation(
                agent_run_id=run_id,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table="main.bronze.t",
                input_sha=None,
                rows_affected=1,
                delta_version_before=0,
                delta_version_after=1,
                started_at=day,
                finished_at=day,
            )
            session.add(op)
            session.flush()
            session.add(
                LineageRowReject(
                    run_id=run_id,
                    op_id=op.id,
                    source_table="main.bronze.t_raw",
                    source_row_id="r1",
                    reason="schema_mismatch",
                    created_at=day,
                )
            )
        session.commit()


def _add_spike_run(*, run_id: str, reject_count: int) -> None:
    """Insert a queued run with a fresh op + N rejects for today."""
    factory = app.state.session_factory
    today = dt.datetime.now(dt.UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="spike@test.com",
                agent_id="spiker",
                notebook_path="spike.py",
                source_snapshot_sha="0" * 64,
                status="running",
                started_at=today,
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.bronze.t",
            input_sha=None,
            rows_affected=reject_count,
            delta_version_before=0,
            delta_version_after=1,
            started_at=today,
            finished_at=today,
        )
        session.add(op)
        session.flush()
        for i in range(reject_count):
            session.add(
                LineageRowReject(
                    run_id=run_id,
                    op_id=op.id,
                    source_table="main.bronze.t_raw",
                    source_row_id=f"r{i}",
                    reason="schema_mismatch",
                    created_at=today,
                )
            )
        session.commit()


@pytest.mark.asyncio
async def test_finish_handler_persists_anomaly_severity(admin_client: httpx.AsyncClient) -> None:
    """``POST /api/agent-runs/{run_id}/finish`` writes the verdict."""
    _seed_baseline()
    run_id = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    _add_spike_run(run_id=run_id, reject_count=200)

    r = await admin_client.post(
        f"/api/agent-runs/{run_id}/finish",
        json={"status": "succeeded"},
    )
    assert r.status_code == 200, r.text

    factory = app.state.session_factory
    with factory() as session:
        row = session.query(AgentRun).filter_by(id=run_id).one()
        assert row.anomaly_severity in ("warn", "critical")
        assert row.anomaly_metric == "rejects"


@pytest.mark.asyncio
async def test_finish_handler_quiet_run_marks_ok(admin_client: httpx.AsyncClient) -> None:
    """A quiet run finishing keeps ``anomaly_severity='ok'``."""
    run_id = "00000000-0000-0000-0000-000000000001"
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="quiet@test.com",
                agent_id="quiet",
                notebook_path="quiet.py",
                source_snapshot_sha="0" * 64,
                status="running",
                started_at=dt.datetime.now(dt.UTC),
            )
        )
        session.commit()

    r = await admin_client.post(
        f"/api/agent-runs/{run_id}/finish",
        json={"status": "succeeded"},
    )
    assert r.status_code == 200, r.text

    with factory() as session:
        row = session.query(AgentRun).filter_by(id=run_id).one()
        assert row.anomaly_severity == "ok"
        assert row.anomaly_metric is None


def test_backfill_run_anomalies_fills_existing_rows() -> None:
    """``backfill_run_anomalies`` updates ``anomaly_severity`` for legacy rows."""
    _seed_baseline()
    run_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    _add_spike_run(run_id=run_id, reject_count=200)

    factory = app.state.session_factory
    with factory() as session:
        row = session.query(AgentRun).filter_by(id=run_id).one()
        row.status = "succeeded"
        row.finished_at = row.started_at
        session.commit()

    written = agg.backfill_run_anomalies(factory)
    assert written >= 1

    with factory() as session:
        row = session.query(AgentRun).filter_by(id=run_id).one()
        assert row.anomaly_severity in ("warn", "critical")
        assert row.anomaly_metric == "rejects"


@pytest.mark.asyncio
async def test_runs_list_serializer_exposes_anomaly_fields(admin_client: httpx.AsyncClient) -> None:
    """``GET /api/runs`` includes anomaly_severity + anomaly_metric."""
    _seed_baseline()
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    _add_spike_run(run_id=run_id, reject_count=200)

    await admin_client.post(
        f"/api/agent-runs/{run_id}/finish",
        json={"status": "succeeded"},
    )
    r = await admin_client.get("/api/runs")
    assert r.status_code == 200
    runs = r.json()["runs"]
    target = next(run for run in runs if run["id"] == run_id)
    assert target["anomaly_severity"] in ("warn", "critical")
    assert target["anomaly_metric"] == "rejects"


@pytest.mark.asyncio
async def test_runs_list_html_renders_badge(admin_client: httpx.AsyncClient) -> None:
    """``GET /runs`` renders the anomaly badge column."""
    _seed_baseline()
    run_id = "ddddddee-eeee-eeee-eeee-eeeeeeeeeeee"
    _add_spike_run(run_id=run_id, reject_count=200)

    await admin_client.post(f"/api/agent-runs/{run_id}/finish", json={"status": "succeeded"})
    r = await admin_client.get("/runs")
    assert r.status_code == 200
    assert ">Anomaly</th>" in r.text
    assert "data-sort-anomaly=" in r.text
