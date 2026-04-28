"""Tests for Sprint 18.5 anomaly surfaces.

Three surfaces:

* ``/api/home/summary`` carries an ``anomalies`` block.
* ``/runs/{id}`` HTML renders the anomaly chip when the latest
  reject day breaches the configured σ threshold.
* The home page banner appears when ``critical >= 1``.

The aggregator math is already covered in
:mod:`tests.test_audit_aggregator`; here we focus on the wiring.
"""

from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunSource,
    LineageRowReject,
)
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture(autouse=True)
def _stub_uc_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the soyuz client + ``for_principal`` so the home page
    renders without reaching out to a live soyuz.
    """
    fake = MagicMock(spec=UnityCatalogClient)
    fake.list_catalogs = AsyncMock(return_value=[])
    fake.list_connections = AsyncMock(return_value=[])
    fake.get_tags = AsyncMock(return_value=[])
    app.state.uc_client = fake
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),
    )


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_anomalous_rejects(*, today_count: int, prior_days: list[int]) -> str:
    """Insert one run per prior day + a sentinel today, with the
    requested reject counts.  Returns today's run id.
    """
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    today_run_id = ""
    with factory() as s:
        for offset, count in enumerate(prior_days, start=1):
            rid = str(uuid.uuid4())
            s.add(
                AgentRun(
                    id=rid,
                    principal="alice@example.com",
                    agent_id="etl",
                    notebook_path="x.py",
                    status="succeeded",
                    started_at=now - datetime.timedelta(days=offset),
                    finished_at=now - datetime.timedelta(days=offset),
                )
            )
            op = AgentRunOperation(
                agent_run_id=rid,
                ordinal=1,
                op_name="merge",
                params_json="{}",
                target_table="cat.sch.t",
                rows_affected=10,
                started_at=now - datetime.timedelta(days=offset),
                finished_at=now - datetime.timedelta(days=offset),
            )
            s.add(op)
            s.flush()
            for j in range(count):
                s.add(
                    LineageRowReject(
                        run_id=rid,
                        op_id=op.id,
                        source_table="cat.sch.bronze",
                        source_row_id=f"prior{offset}_{j}",
                        reason="on_key_null",
                        created_at=now - datetime.timedelta(days=offset),
                    )
                )
        # Today's run
        today_run_id = str(uuid.uuid4())
        s.add(
            AgentRun(
                id=today_run_id,
                principal="alice@example.com",
                agent_id="etl",
                notebook_path="x.py",
                status="succeeded",
                started_at=now,
                finished_at=now,
            )
        )
        s.add(
            AgentRunSource(
                agent_run_id=today_run_id,
                source_bytes="print('seed')\n",
                source_sha="0" * 64,
                captured_at=now,
            )
        )
        op_today = AgentRunOperation(
            agent_run_id=today_run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat.sch.t",
            rows_affected=10,
            started_at=now,
            finished_at=now,
        )
        s.add(op_today)
        s.flush()
        for j in range(today_count):
            s.add(
                LineageRowReject(
                    run_id=today_run_id,
                    op_id=op_today.id,
                    source_table="cat.sch.bronze",
                    source_row_id=f"today_{j}",
                    reason="on_key_null",
                    created_at=now,
                )
            )
        s.commit()
    return today_run_id


# ---------------------------------------------------------------------
# /api/home/summary anomalies block
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_home_summary_includes_anomalies_block() -> None:
    async with _admin_client() as client:
        r = await client.get("/api/home/summary")
    assert r.status_code == 200
    body = r.json()
    assert "anomalies" in body
    assert "warn" in body["anomalies"]
    assert "critical" in body["anomalies"]


@pytest.mark.asyncio
async def test_home_summary_anomalies_critical_for_synthetic_spike() -> None:
    _seed_anomalous_rejects(today_count=50, prior_days=[2, 3, 1, 2, 4, 2, 3])
    async with _admin_client() as client:
        r = await client.get("/api/home/summary")
    body = r.json()
    # Today has 50 rejects against a calm baseline.  Aggregator
    # marks that "critical" given the >2σ rule.
    assert body["anomalies"]["critical"] >= 1


# ---------------------------------------------------------------------
# Home HTML banner
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_home_html_renders_anomaly_banner_on_critical() -> None:
    _seed_anomalous_rejects(today_count=50, prior_days=[2, 3, 1, 2, 4, 2, 3])
    async with _admin_client() as client:
        r = await client.get("/")
    assert r.status_code == 200
    body = r.text
    assert "Sprint 18.5 — anomaly highlighting" in body
    assert "Open audit cockpit" in body


@pytest.mark.asyncio
async def test_home_html_no_banner_when_baseline_steady() -> None:
    _seed_anomalous_rejects(today_count=2, prior_days=[2, 3, 1, 2, 4, 2, 3])
    async with _admin_client() as client:
        r = await client.get("/")
    assert r.status_code == 200
    assert "Sprint 18.5 — anomaly highlighting" not in r.text


# ---------------------------------------------------------------------
# Run-detail anomaly chip
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detail_renders_anomaly_chip_on_critical() -> None:
    today_run = _seed_anomalous_rejects(
        today_count=50, prior_days=[2, 3, 1, 2, 4, 2, 3]
    )
    async with _admin_client() as client:
        r = await client.get(f"/runs/{today_run}")
    assert r.status_code == 200
    body = r.text
    assert "Sprint 18.5 — anomaly chip" in body
    assert "rejects" in body  # metric name shows up


@pytest.mark.asyncio
async def test_run_detail_no_chip_when_steady() -> None:
    today_run = _seed_anomalous_rejects(
        today_count=2, prior_days=[2, 3, 1, 2, 4, 2, 3]
    )
    async with _admin_client() as client:
        r = await client.get(f"/runs/{today_run}")
    assert r.status_code == 200
    assert "Sprint 18.5 — anomaly chip" not in r.text
