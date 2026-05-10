"""Sprint 29.1 — per-workspace audit-sink routing.

Pins the four invariants that protect tenants from cross-workspace
webhook leaks:

1. ``workspace_filter=None`` keeps install-global semantics — the
   sink fires for every workspace's events (back-compat).
2. ``workspace_filter=[1]`` skips events whose ``workspace_id=2``.
3. ``workspace_filter=[1, 2]`` accepts both workspaces.
4. The admin route rejects unknown workspace IDs at validation time
   so a typo never silently blackholes deliveries.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import Workspace
from pointlessql.models.audit._sinks import AuditSink
from pointlessql.services.audit.sinks import _select_active_sinks


def _factory():
    return app.state.session_factory


def _make_sink(
    *,
    name: str,
    workspace_filter: list[int] | None,
) -> int:
    """Insert an active webhook sink and return its primary key.

    Uses a placeholder URL the dispatcher never reaches in these
    tests — we only exercise ``_select_active_sinks``, which short-
    circuits before any HTTP call.
    """
    factory = _factory()
    with factory() as session:
        row = AuditSink(
            name=name,
            type="webhook",
            config_json=json.dumps({"url": "https://example.invalid/hook"}),
            is_active=True,
            event_types_json=None,
            workspace_filter=(
                json.dumps(workspace_filter) if workspace_filter is not None else None
            ),
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


def _seed_workspace(slug: str, name: str) -> int:
    """Insert a non-default workspace row and return its id."""
    factory = _factory()
    with factory() as session:
        ws = Workspace(
            slug=slug,
            name=name,
            description="Test fixture for Sprint 29.1.",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


# ---------------------------------------------------------------------------
# Dispatcher predicate — the load-bearing path for the routing fix
# ---------------------------------------------------------------------------


def test_null_workspace_filter_dispatches_all_workspaces() -> None:
    """Back-compat: a null filter fires for every workspace's events."""
    sink_id = _make_sink(name="all-events-sink", workspace_filter=None)
    factory = _factory()
    with factory() as session:
        for ws_id in (1, 2, 999):
            sinks = _select_active_sinks(
                session, event_type="pointlessql.policy.violated", workspace_id=ws_id
            )
            assert any(s.id == sink_id for s in sinks), (
                f"null workspace_filter must accept workspace_id={ws_id}"
            )


def test_single_workspace_filter_skips_other_workspaces() -> None:
    """``workspace_filter=[1]`` excludes workspace_id=2."""
    other_ws = _seed_workspace("filter-skip-a", "Filter Skip A")
    sink_id = _make_sink(name="ws1-only-sink", workspace_filter=[1])
    factory = _factory()
    with factory() as session:
        sinks_ws1 = _select_active_sinks(
            session, event_type="pointlessql.policy.violated", workspace_id=1
        )
        sinks_other = _select_active_sinks(
            session, event_type="pointlessql.policy.violated", workspace_id=other_ws
        )
    assert any(s.id == sink_id for s in sinks_ws1)
    assert not any(s.id == sink_id for s in sinks_other), (
        "workspace_filter=[1] must NOT fire for workspace_id={other_ws}"
    )


def test_multi_workspace_filter_accepts_both() -> None:
    """``workspace_filter=[1,2]`` accepts both listed workspaces."""
    other_ws = _seed_workspace("filter-multi-a", "Filter Multi A")
    sink_id = _make_sink(name="ws1-and-ws2-sink", workspace_filter=[1, other_ws])
    factory = _factory()
    with factory() as session:
        for ws_id in (1, other_ws):
            sinks = _select_active_sinks(
                session, event_type="pointlessql.policy.violated", workspace_id=ws_id
            )
            assert any(s.id == sink_id for s in sinks), (
                f"multi-filter must accept workspace_id={ws_id}"
            )


# ---------------------------------------------------------------------------
# Route-level validation — typos at create time fail loud, not silent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_rejects_unknown_workspace_id() -> None:
    """Creating a sink with an unknown workspace_id returns 400."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(
            "/api/admin/audit-sinks",
            json={
                "name": "typo-sink",
                "type": "webhook",
                "config": {"url": "https://example.invalid/hook"},
                "workspace_filter": [9999],
            },
        )
    assert response.status_code in (400, 422), response.text
    assert "workspace" in response.text.lower()


@pytest.mark.asyncio
async def test_post_round_trips_workspace_filter() -> None:
    """A valid workspace_filter survives POST → GET round-trip."""
    other_ws = _seed_workspace("filter-rt-a", "Round Trip A")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/audit-sinks",
            json={
                "name": "round-trip-sink",
                "type": "webhook",
                "config": {"url": "https://example.invalid/hook"},
                "workspace_filter": [1, other_ws],
            },
        )
        assert post.status_code == 200, post.text
        assert post.json()["workspace_filter"] == sorted([1, other_ws])
        listing = await client.get("/api/admin/audit-sinks")
    rows = {row["name"]: row for row in listing.json()["sinks"]}
    assert rows["round-trip-sink"]["workspace_filter"] == sorted([1, other_ws])


@pytest.mark.asyncio
async def test_patch_clears_workspace_filter_with_null() -> None:
    """PATCH with ``workspace_filter=null`` reverts to install-global."""
    other_ws = _seed_workspace("filter-clear-a", "Clear A")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/audit-sinks",
            json={
                "name": "clear-sink",
                "type": "webhook",
                "config": {"url": "https://example.invalid/hook"},
                "workspace_filter": [other_ws],
            },
        )
        sink_id = post.json()["id"]
        patch = await client.patch(
            f"/api/admin/audit-sinks/{sink_id}",
            json={"workspace_filter": None},
        )
    assert patch.status_code == 200, patch.text
    assert patch.json()["workspace_filter"] is None
