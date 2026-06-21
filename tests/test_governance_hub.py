"""Tests for the governance-hub posture + remediation aggregator."""

from __future__ import annotations

import datetime
import json
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import AuditLog, Workspace
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services import governance_hub


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"ghub-{uuid.uuid4().hex[:10]}",
            name="Governance hub test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _seed_violation(ws: int, *, severity: str, table: str, kind: str = "unclassified_pii") -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            AuditLog(
                workspace_id=ws,
                user_id=0,
                user_email="system",
                actor_role="system",
                action=governance_hub.COMPLIANCE_VIOLATION_ACTION,
                target=f"data_product:main.{table}",
                detail=json.dumps(
                    {"kind": kind, "table": table, "severity": severity, "message": "fix me"}
                ),
                created_at=now,
            )
        )
        session.commit()


def _seed_anomaly_run(ws: int, *, severity: str, metric: str = "rejects") -> None:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            AgentRun(
                id=uuid.uuid4().hex,
                workspace_id=ws,
                notebook_path="demo/run.py",
                status="succeeded",
                started_at=now,
                anomaly_severity=severity,
                anomaly_metric=metric,
            )
        )
        session.commit()


def test_posture_scores_and_ranks() -> None:
    ws = _fresh_workspace()
    _seed_violation(ws, severity="critical", table="t1")
    _seed_violation(ws, severity="warn", table="t2")
    _seed_anomaly_run(ws, severity="critical")

    out = governance_hub.governance_posture(_factory(), workspace_id=ws)

    assert out["totals"]["findings"] == 3
    assert out["totals"]["critical"] == 2
    assert out["totals"]["warn"] == 1
    assert out["totals"]["compliance"] == 2
    assert out["totals"]["anomaly"] == 1
    # penalty = 12*2 + 4*1 = 28 → 72 → grade C.
    assert out["posture_score"] == 72
    assert out["grade"] == "C"
    # Critical findings rank ahead of warnings in the queue.
    assert out["remediation_queue"][0]["severity"] == "critical"
    assert out["remediation_queue"][-1]["severity"] == "warn"


def test_posture_dedupes_recurring_findings() -> None:
    ws = _fresh_workspace()
    # The scanner re-logs the same finding on every run.
    _seed_violation(ws, severity="critical", table="t1")
    _seed_violation(ws, severity="critical", table="t1")
    _seed_violation(ws, severity="critical", table="t1")

    out = governance_hub.governance_posture(_factory(), workspace_id=ws)

    assert out["totals"]["findings"] == 1
    assert out["totals"]["critical"] == 1


def test_posture_clean_workspace_is_perfect() -> None:
    ws = _fresh_workspace()
    out = governance_hub.governance_posture(_factory(), workspace_id=ws)
    assert out["posture_score"] == 100
    assert out["grade"] == "A"
    assert out["remediation_queue"] == []


def test_posture_penalty_caps_at_zero() -> None:
    ws = _fresh_workspace()
    for i in range(20):
        _seed_violation(ws, severity="critical", table=f"t{i}")
    out = governance_hub.governance_posture(_factory(), workspace_id=ws)
    assert out["posture_score"] == 0
    assert out["grade"] == "F"


@pytest.mark.asyncio
async def test_route_posture(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/admin/governance-hub/posture")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"posture_score", "grade", "totals", "remediation_queue"} <= set(data)


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/admin/governance-hub")
    assert resp.status_code == 200, resp.text
    assert "Governance hub" in resp.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/admin/governance-hub/posture")
    assert resp.status_code in {401, 403}
