"""Route tests for the agent command center cockpit.

Covers the HTML page render, the live-thread / candidate-set summary,
the side-by-side compare endpoint (including the skip-unknown contract),
and the auth gate.  Runs are seeded through the public registration
endpoint so the tests exercise the same path the runtime uses.
"""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import Workspace
from pointlessql.models.agent._runs import AgentRun


def _seed_foreign_run(notebook_path: str) -> str:
    """Insert an agent run in a brand-new (non-default) workspace.

    Returns the run id so a test can prove the default-workspace cockpit
    refuses to surface it.
    """
    now = datetime.datetime.now(datetime.UTC)
    factory = fastapi_app.state.session_factory
    run_id = f"ccf{uuid.uuid4().hex[:5]}-0000-0000-0000-{uuid.uuid4().hex[:12]}"
    with factory() as session:
        ws = Workspace(slug=f"cc-{uuid.uuid4().hex[:10]}", name="Other WS", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=int(ws.id),
                notebook_path=notebook_path,
                status="succeeded",
                started_at=now,
            )
        )
        session.commit()
    return run_id


async def _register_run(
    client: httpx.AsyncClient,
    *,
    run_id: str,
    notebook_path: str,
    status: str = "queued",
) -> None:
    """Register one agent run with an explicit status and notebook path.

    Args:
        client: Authenticated async client.
        run_id: Caller-chosen UUID for the run.
        notebook_path: Path the run is attributed to (drives grouping).
        status: Initial run status (``queued`` keeps the run live).
    """
    response = await client.post(
        "/api/agent-runs",
        json={
            "id": run_id,
            "notebook_path": notebook_path,
            "source": f"# {run_id}\nprint('seed')\n",
            "runtime_versions": {"python": "3.14.0"},
            "status": status,
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_command_center_page_renders(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/command-center")
    assert response.status_code == 200, response.text
    assert "Agent Command Center" in response.text


@pytest.mark.asyncio
async def test_summary_lists_live_run(admin_client: httpx.AsyncClient) -> None:
    run_id = "cc111111-1111-1111-1111-111111111111"
    await _register_run(
        admin_client, run_id=run_id, notebook_path="demo/cc_live.py", status="running"
    )

    response = await admin_client.get("/api/command-center/summary")
    assert response.status_code == 200, response.text
    payload = response.json()

    live_ids = {run["id"] for run in payload["live"]}
    assert run_id in live_ids
    assert payload["counts"]["live"] >= 1


@pytest.mark.asyncio
async def test_summary_groups_candidate_runs(admin_client: httpx.AsyncClient) -> None:
    path = "demo/cc_candidates.py"
    ids = [
        "cc222221-2222-2222-2222-222222222222",
        "cc222222-2222-2222-2222-222222222222",
    ]
    for run_id in ids:
        await _register_run(admin_client, run_id=run_id, notebook_path=path)

    response = await admin_client.get("/api/command-center/summary")
    assert response.status_code == 200, response.text
    payload = response.json()

    groups = {group["notebook_path"]: group for group in payload["candidate_groups"]}
    assert path in groups
    group = groups[path]
    assert group["size"] >= 2
    grouped_ids = {run["id"] for run in group["runs"]}
    assert set(ids) <= grouped_ids


@pytest.mark.asyncio
async def test_compare_returns_columns_and_skips_unknown(
    admin_client: httpx.AsyncClient,
) -> None:
    ids = [
        "cc333331-3333-3333-3333-333333333333",
        "cc333332-3333-3333-3333-333333333333",
    ]
    for run_id in ids:
        await _register_run(admin_client, run_id=run_id, notebook_path="demo/cc_compare.py")

    unknown = "cc999999-9999-9999-9999-999999999999"
    response = await admin_client.get(
        "/api/command-center/compare",
        params={"run_ids": f"{ids[0]},{ids[1]},{unknown}"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    returned = [column["id"] for column in payload["runs"]]
    assert returned == ids  # order preserved, unknown skipped
    first = payload["runs"][0]
    assert first["op_count"] == 0
    assert first["errored_ops"] == 0
    assert "duration_ms" in first


@pytest.mark.asyncio
async def test_compare_skips_foreign_workspace_run(admin_client: httpx.AsyncClient) -> None:
    # A run id from another workspace must not be pulled into the
    # default-workspace cockpit comparison.
    mine = "cc444441-4444-4444-4444-444444444444"
    await _register_run(admin_client, run_id=mine, notebook_path="demo/cc_iso.py")
    foreign = _seed_foreign_run("demo/cc_iso.py")

    response = await admin_client.get(
        "/api/command-center/compare", params={"run_ids": f"{mine},{foreign}"}
    )
    assert response.status_code == 200, response.text
    returned = [column["id"] for column in response.json()["runs"]]
    assert returned == [mine]  # foreign workspace run silently dropped


@pytest.mark.asyncio
async def test_compare_empty_selection_is_ok(admin_client: httpx.AsyncClient) -> None:
    response = await admin_client.get("/api/command-center/compare")
    assert response.status_code == 200, response.text
    assert response.json()["runs"] == []


@pytest.mark.asyncio
async def test_command_center_requires_auth(anonymous_client: httpx.AsyncClient) -> None:
    response = await anonymous_client.get("/command-center", follow_redirects=False)
    assert response.status_code in {302, 303, 307, 401, 403}
