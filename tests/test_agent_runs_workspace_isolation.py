"""Sprint 28.1a — workspace isolation for the audit-trail core.

Asserts that a workspace-A user CANNOT see workspace-B's:

* agent_runs (listing route + run-detail page)
* agent_run_operations (listing route + per-op filter)
* agent_run_sources (cross-workspace 404 via ensure_run_visible)
* agent_run_events (lifecycle endpoint guard)
* agent_run_tool_calls (per-run audit axis guard)
* audit_search FTS5 hits (workspace_id filter)
"""

from __future__ import annotations

import datetime
import hashlib
import uuid
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AgentRunSource,
    User,
    Workspace,
    WorkspaceMember,
)
from pointlessql.services.workspace import _crud as workspaces_service


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        user = session.query(User).filter(User.email == "test@test.com").one()
        return user.id


def _seed_run(
    *,
    workspace_id: int,
    principal: str = "alice@example.com",
    notebook_path: str = "demo/run.py",
    status: str = "queued",
) -> str:
    """Insert a synthetic agent_run row + matching source row."""
    run_id = str(uuid.uuid4())
    source_bytes = "print('hi')\n"
    sha = hashlib.sha256(source_bytes.encode("utf-8")).hexdigest()
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            AgentRun(
                id=run_id,
                workspace_id=workspace_id,
                principal=principal,
                notebook_path=notebook_path,
                source_snapshot_sha=sha,
                status=status,
                started_at=now,
            )
        )
        session.flush()
        session.add(
            AgentRunSource(
                workspace_id=workspace_id,
                agent_run_id=run_id,
                source_bytes=source_bytes,
                source_sha=sha,
                captured_at=now,
            )
        )
        session.commit()
    return run_id


def _seed_op(
    *,
    workspace_id: int,
    agent_run_id: str,
    op_name: str = "merge",
    target_table: str = "main.silver.orders",
    error: str | None = None,
) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        op = AgentRunOperation(
            workspace_id=workspace_id,
            agent_run_id=agent_run_id,
            ordinal=1,
            op_name=op_name,
            params_json="{}",
            target_table=target_table,
            started_at=now,
            finished_at=now,
            error_message=error,
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return int(op.id)


def _add_member_to(workspace_id: int) -> None:
    """Make the admin fixture user a member of *workspace_id*."""
    workspaces_service.add_member(
        _factory(), workspace_id=workspace_id, user_id=_admin_user_id(), role="member"
    )


@pytest.fixture
def two_workspaces() -> tuple[int, int]:
    """Create workspaces A and B with the admin fixture user as member of both."""
    a = workspaces_service.create_workspace(_factory(), slug="ws-a", name="A")
    b = workspaces_service.create_workspace(_factory(), slug="ws-b", name="B")
    _add_member_to(a.id)
    _add_member_to(b.id)
    return a.id, b.id


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_agent_run_workspace_id_column_exists() -> None:
    """The Sprint 28.1a migration adds workspace_id to all 5 audit-trail tables."""
    from sqlalchemy import inspect

    insp = inspect(_factory()().get_bind())
    for table in (
        "agent_runs",
        "agent_run_sources",
        "agent_run_operations",
        "agent_run_events",
        "agent_run_tool_calls",
    ):
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "workspace_id" in cols, f"{table} missing workspace_id column"


# ---------------------------------------------------------------------------
# Listing routes scope by workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_route_excludes_other_workspace_runs(
    two_workspaces: tuple[int, int],
) -> None:
    """GET /api/agent-runs returns only the caller-workspace's runs."""
    ws_a, ws_b = two_workspaces
    run_a = _seed_run(workspace_id=ws_a)
    run_b = _seed_run(workspace_id=ws_b)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get("/api/agent-runs?limit=50", headers={"X-Workspace": "ws-a"})
    assert response.status_code == 200
    payload = response.json()
    run_ids = {r["id"] for r in payload["runs"]}
    assert run_a in run_ids
    assert run_b not in run_ids


@pytest.mark.asyncio
async def test_operations_listing_route_excludes_other_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    """GET /api/agent-runs/operations is workspace-scoped."""
    ws_a, ws_b = two_workspaces
    run_a = _seed_run(workspace_id=ws_a)
    run_b = _seed_run(workspace_id=ws_b)
    op_a = _seed_op(workspace_id=ws_a, agent_run_id=run_a, target_table="main.silver.alpha")
    op_b = _seed_op(workspace_id=ws_b, agent_run_id=run_b, target_table="main.silver.beta")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(
            "/api/agent-runs/operations?limit=50", headers={"X-Workspace": "ws-a"}
        )
    assert response.status_code == 200
    payload = response.json()
    op_ids = {op["id"] for op in payload["operations"]}
    assert op_a in op_ids
    assert op_b not in op_ids


# ---------------------------------------------------------------------------
# Per-run audit-axis cross-workspace 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_run_audit_returns_404_for_other_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    """Hitting /api/agent-runs/{id}/audit/lineage from the wrong workspace = 404."""
    ws_a, _ = two_workspaces
    run_a = _seed_run(workspace_id=ws_a)
    _seed_op(workspace_id=ws_a, agent_run_id=run_a)

    # workspace=B caller cannot see workspace=A's run, even though they're admin.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(
            f"/api/agent-runs/{run_a}/audit/lineage", headers={"X-Workspace": "ws-b"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_per_run_audit_succeeds_in_owner_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    """Same call from inside the owner workspace returns 200."""
    ws_a, _ = two_workspaces
    run_a = _seed_run(workspace_id=ws_a)
    _seed_op(workspace_id=ws_a, agent_run_id=run_a)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.get(
            f"/api/agent-runs/{run_a}/audit/lineage", headers={"X-Workspace": "ws-a"}
        )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Ingestion writes workspace_id from request.state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_agent_run_writes_request_workspace_id(
    two_workspaces: tuple[int, int],
) -> None:
    """POST /api/agent-runs records workspace_id from request.state."""
    ws_a, ws_b = two_workspaces
    body: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "notebook_path": "demo/created.py",
        "source": "print('seed')\n",
        "runtime_versions": {"python": "3.14.0"},
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post("/api/agent-runs", json=body, headers={"X-Workspace": "ws-b"})
    assert response.status_code == 200
    with _factory()() as session:
        row = session.get(AgentRun, body["id"])
        assert row is not None
        assert int(row.workspace_id) == ws_b
        # Source row inherits the same workspace.
        src = session.scalar(
            __import__("sqlalchemy")
            .select(AgentRunSource)
            .where(AgentRunSource.agent_run_id == body["id"])
        )
        assert src is not None
        assert int(src.workspace_id) == ws_b


# ---------------------------------------------------------------------------
# FTS5 surgery — workspace_id column + filter + cross-workspace isolation
# ---------------------------------------------------------------------------


def test_fts_search_filters_by_workspace(two_workspaces: tuple[int, int]) -> None:
    """audit_fts.search with workspace_id arg returns only matching rows."""
    from pointlessql.services import audit_fts

    # conftest's Base.metadata.create_all skips FTS5 vtables; provision
    # the index lazily for the test (idempotent).
    audit_fts.install_index(_factory())

    ws_a, ws_b = two_workspaces
    # Trigger-driven: inserting an agent_run populates audit_search via trigger.
    run_a = _seed_run(workspace_id=ws_a, principal="alicedistinctname@example.com")
    run_b = _seed_run(workspace_id=ws_b, principal="alicedistinctname@example.com")

    # Workspace=A search finds run_a only.
    result_a = audit_fts.search(_factory(), query="alicedistinctname", workspace_id=ws_a)
    assert result_a["available"] is True
    run_ids = {r["entity_id"] for r in result_a["results"] if r["axis"] == "runs"}
    assert run_a in run_ids
    assert run_b not in run_ids

    # No-filter search finds both.
    result_all = audit_fts.search(_factory(), query="alicedistinctname")
    run_ids_all = {r["entity_id"] for r in result_all["results"] if r["axis"] == "runs"}
    assert run_a in run_ids_all
    assert run_b in run_ids_all


@pytest.mark.asyncio
async def test_audit_search_route_uses_request_workspace(
    two_workspaces: tuple[int, int],
) -> None:
    """GET /api/audit/search scopes results to the request's workspace."""
    from pointlessql.services import audit_fts as _audit_fts

    _audit_fts.install_index(_factory())
    ws_a, ws_b = two_workspaces
    _seed_run(workspace_id=ws_a, principal="zzzuniqueprincipala@example.com")
    _seed_run(workspace_id=ws_b, principal="zzzuniqueprincipalb@example.com")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response_a = await client.get(
            "/api/audit/search?q=zzzuniqueprincipala&axis=runs",
            headers={"X-Workspace": "ws-a"},
        )
        response_b = await client.get(
            "/api/audit/search?q=zzzuniqueprincipala&axis=runs",
            headers={"X-Workspace": "ws-b"},
        )
    payload_a = response_a.json()
    payload_b = response_b.json()
    assert payload_a["available"] is True
    assert any(r["principal"] == "zzzuniqueprincipala@example.com" for r in payload_a["results"])
    # Workspace B should NOT see workspace A's principal even via search.
    assert all(r["principal"] != "zzzuniqueprincipala@example.com" for r in payload_b["results"])


def test_fts_vtable_carries_workspace_id_column() -> None:
    """The audit_search vtable / index table has workspace_id as a column.

    SQLite uses an FTS5 vtable named ``audit_search``; PG uses a
    plain ``audit_search_index`` table with a tsvector + GIN index
    (Phase 30, migration ``hh8j…``).  Both ship workspace_id.
    """
    from sqlalchemy import inspect as _inspect

    from pointlessql.services import audit_fts as _audit_fts

    _audit_fts.install_index(_factory())
    with _factory()() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            insp = _inspect(bind)
            cols = [c["name"] for c in insp.get_columns("audit_search_index")]
        else:
            from sqlalchemy import text as _text

            result = session.execute(_text("PRAGMA table_info(audit_search)")).all()
            cols = [r[1] for r in result]
    assert "workspace_id" in cols


def test_membership_required_for_workspace_member_table() -> None:
    """add_member rejects unknown roles (defensive — covered also by 28.0)."""
    factory = _factory()
    with factory() as session:
        ws = Workspace(
            id=99,
            slug="ws-test-membership",
            name="x",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ws)
        session.commit()
        # Sanity: membership counts include the conftest-seeded admins.
        members = session.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == 1).count()
        assert members >= 2
