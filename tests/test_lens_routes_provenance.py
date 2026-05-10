"""HTTP smoke for GET /api/lens/provenance (Sprint 65.1)."""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageRowEdge,
)


@pytest.mark.asyncio
async def test_provenance_route_returns_trace_for_anonymous_user_blocked(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous caller hits 401/403 because require_analyst is gated."""
    resp = await anonymous_client.get(
        "/api/lens/provenance",
        params={"table_fqn": "main.silver.t"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_provenance_route_returns_trace_for_admin(
    admin_client: httpx.AsyncClient,
) -> None:
    """Admin (strictly stronger than analyst) gets a populated trace."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as s:
        s.add(
            AgentRun(
                id="lens-route-test-run",
                principal="test",
                agent_id="lens-route-test",
                notebook_path="lens_route.py",
                status="running",
                started_at=now,
            )
        )
        s.flush()
        op = AgentRunOperation(
            agent_run_id="lens-route-test-run",
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="main.silver.routes_t",
            started_at=now,
        )
        s.add(op)
        s.commit()
        s.refresh(op)
        op_id = op.id
        s.add(
            LineageRowEdge(
                run_id="lens-route-test-run",
                op_id=op_id,
                source_table="main.bronze.routes_t",
                source_row_id="b1",
                target_table="main.silver.routes_t",
                target_row_id="s1",
                created_at=now,
            )
        )
        s.commit()

    resp = await admin_client.get(
        "/api/lens/provenance",
        params={
            "table_fqn": "main.silver.routes_t",
            "row_id": "s1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "row"
    assert any(s["table_fqn"] == "main.bronze.routes_t" for s in body["sources"])
