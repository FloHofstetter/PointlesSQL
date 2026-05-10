"""Sprint 28.7 — cross-workspace super-admin lens.

The audit aggregator (and the three /api/audit/* routes that wrap
it) gained a ``workspace_id`` filter.  By default every call scopes
to the request's resolved workspace.  Tenant admins may opt into:

* ``?workspace=all`` — the cross-workspace lens; aggregator runs
  without a workspace filter.  Logged with
  ``read_kind='audit_api_cross_workspace'`` so the audit-of-audit
  trail flags the escalation.
* ``?workspace=<slug>`` — scope to a named workspace, regardless
  of the request's resolved one.

Non-admin callers asking for either form get 403.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AgentRun, QueryHistory
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def _make_run(workspace_id: int, principal: str = "test-principal") -> str:
    """Insert one minimal AgentRun row in *workspace_id* and return its id."""
    rid = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            AgentRun(
                id=rid,
                principal=principal,
                started_at=now,
                status="completed",
                source_snapshot_sha="x" * 64,
                notebook_path="lens-test.py",
                workspace_id=workspace_id,
            )
        )
        session.commit()
    return rid


@pytest.fixture
def two_workspaces_with_runs():
    """Default workspace stays seeded; create a second workspace + one run each."""
    other = workspaces_service.create_workspace(_factory(), slug="ws-lens-b", name="Lens B")
    run_default = _make_run(workspace_id=1, principal="alice")
    run_other = _make_run(workspace_id=other.id, principal="bob")
    return {
        "default_id": 1,
        "other_id": other.id,
        "default_run": run_default,
        "other_run": run_other,
    }


@pytest.mark.asyncio
async def test_summary_default_scopes_to_current_workspace(
    two_workspaces_with_runs: dict,
) -> None:
    """No ?workspace= → caller sees only their workspace's runs."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/api/audit/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["lens_mode"] == "current"
    # Admin user defaults to workspace 1; only run_default counts.
    # The seeded fixtures might add other rows too — assert only that
    # principal "bob" (workspace 2's run) is NOT visible by way of
    # cross-workspace counts being lower than the all-workspaces total.
    counts_current = body["counts"]["runs"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        all_response = await client.get("/api/audit/summary?workspace=all")
    assert all_response.status_code == 200
    all_body = all_response.json()
    assert all_body["lens_mode"] == "all"
    counts_all = all_body["counts"]["runs"]

    assert counts_all > counts_current, (
        f"cross-workspace lens should see more runs ({counts_all}) "
        f"than the workspace-1 lens ({counts_current})"
    )


@pytest.mark.asyncio
async def test_summary_named_workspace_admin_only(
    two_workspaces_with_runs: dict,
) -> None:
    """Admin can target ws-lens-b by slug; non-admin gets 403."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as admin:
        admin_resp = await admin.get("/api/audit/summary?workspace=ws-lens-b")
    assert admin_resp.status_code == 200
    assert admin_resp.json()["lens_mode"] == "named"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as non_admin:
        non_admin_resp = await non_admin.get("/api/audit/summary?workspace=ws-lens-b")
    # Non-admin asks for a workspace they're not in → 403.
    assert non_admin_resp.status_code == 403


@pytest.mark.asyncio
async def test_summary_all_workspace_non_admin_403(two_workspaces_with_runs: dict) -> None:
    """Non-admin cannot lift the workspace filter."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        response = await client.get("/api/audit/summary?workspace=all")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_summary_all_workspace_writes_distinct_audit_kind(
    two_workspaces_with_runs: dict,
) -> None:
    """Cross-workspace lens leaves a ``audit_api_cross_workspace`` trail."""
    factory = _factory()
    before = datetime.datetime.now(datetime.UTC)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        await client.get("/api/audit/summary?workspace=all")

    with factory() as session:
        rows = list(
            session.scalars(
                select(QueryHistory).where(
                    QueryHistory.read_kind == "audit_api_cross_workspace",
                    QueryHistory.started_at >= before,
                )
            ).all()
        )
    assert len(rows) >= 1


@pytest.mark.asyncio
async def test_anomalies_threads_workspace_filter(
    two_workspaces_with_runs: dict,
) -> None:
    """The same workspace-lens contract applies to /api/audit/anomalies."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/api/audit/anomalies?metric=runs&window_days=2")
    assert response.status_code == 200
    body = response.json()
    assert body["lens_mode"] == "current"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response_all = await client.get(
            "/api/audit/anomalies?metric=runs&window_days=2&workspace=all"
        )
    assert response_all.status_code == 200
    assert response_all.json()["lens_mode"] == "all"


@pytest.mark.asyncio
async def test_unknown_workspace_slug_404s(two_workspaces_with_runs: dict) -> None:
    """A slug that doesn't resolve gets a clean validation error."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/api/audit/summary?workspace=ws-not-real")
    # ValidationError → 422 in this app's exception mapper.
    assert response.status_code in (400, 422)
