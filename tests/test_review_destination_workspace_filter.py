"""Sprint 29.2 — per-workspace review-destination routing.

Mirrors :mod:`tests.test_audit_sink_workspace_filter` for the agent-
review fan-out path.  Pins three invariants:

1. ``workspace_filter=None`` keeps install-global semantics — every
   workspace's reviews fire the destination (back-compat).
2. ``workspace_filter=[1]`` skips reviews whose ``workspace_id=2``.
3. The admin route rejects unknown workspace IDs at validation time.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import Workspace
from pointlessql.models.agent._reviews import AgentReview, ReviewDestination
from pointlessql.services.review_dispatcher import _select_destinations


def _factory():
    return app.state.session_factory


def _make_destination(
    *,
    name: str,
    workspace_filter: list[int] | None,
    min_severity: str = "ok",
) -> int:
    factory = _factory()
    with factory() as session:
        row = ReviewDestination(
            name=name,
            webhook_url="https://example.invalid/hook",
            hmac_secret=None,
            is_active=True,
            min_severity=min_severity,
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
    factory = _factory()
    with factory() as session:
        ws = Workspace(
            slug=slug,
            name=name,
            description="Test fixture for Sprint 29.2.",
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


# ---------------------------------------------------------------------------
# Dispatcher predicate
# ---------------------------------------------------------------------------


def test_null_workspace_filter_dispatches_all_workspaces() -> None:
    """Back-compat: a null filter fires for every workspace's reviews."""
    dest_id = _make_destination(name="all-reviews-dest", workspace_filter=None)
    factory = _factory()
    with factory() as session:
        for ws_id in (1, 2, 999):
            destinations = _select_destinations(session, severity="warn", workspace_id=ws_id)
            assert any(d.id == dest_id for d in destinations), (
                f"null workspace_filter must accept workspace_id={ws_id}"
            )


def test_single_workspace_filter_skips_other_workspaces() -> None:
    """``workspace_filter=[1]`` excludes workspace_id=2."""
    other_ws = _seed_workspace("rd-skip-a", "RD Skip A")
    dest_id = _make_destination(name="ws1-only-dest", workspace_filter=[1])
    factory = _factory()
    with factory() as session:
        destinations_ws1 = _select_destinations(session, severity="warn", workspace_id=1)
        destinations_other = _select_destinations(session, severity="warn", workspace_id=other_ws)
    assert any(d.id == dest_id for d in destinations_ws1)
    assert not any(d.id == dest_id for d in destinations_other)


def test_severity_gate_still_applies_with_workspace_filter() -> None:
    """A destination with min_severity='critical' still skips warn reviews
    even when workspace_filter accepts the workspace.
    """
    other_ws = _seed_workspace("rd-sev-a", "RD Sev A")
    dest_id = _make_destination(
        name="critical-only-dest",
        workspace_filter=[1, other_ws],
        min_severity="critical",
    )
    factory = _factory()
    with factory() as session:
        warn_dests = _select_destinations(session, severity="warn", workspace_id=1)
        crit_dests = _select_destinations(session, severity="critical", workspace_id=other_ws)
    assert not any(d.id == dest_id for d in warn_dests), (
        "min_severity gate must still skip warn reviews"
    )
    assert any(d.id == dest_id for d in crit_dests), (
        "critical reviews must reach the destination when workspace_filter passes"
    )


# ---------------------------------------------------------------------------
# Route-level validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_rejects_unknown_workspace_id() -> None:
    """Creating a destination with an unknown workspace_id returns 400."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        response = await client.post(
            "/api/admin/review-destinations",
            json={
                "name": "rd-typo",
                "webhook_url": "https://example.invalid/hook",
                "workspace_filter": [9999],
            },
        )
    assert response.status_code in (400, 422), response.text
    assert "workspace" in response.text.lower()


@pytest.mark.asyncio
async def test_post_round_trips_workspace_filter() -> None:
    """A valid workspace_filter survives POST → GET round-trip."""
    other_ws = _seed_workspace("rd-rt-a", "RD Round Trip A")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/review-destinations",
            json={
                "name": "rd-round-trip",
                "webhook_url": "https://example.invalid/hook",
                "workspace_filter": [1, other_ws],
            },
        )
        assert post.status_code == 200, post.text
        assert post.json()["workspace_filter"] == sorted([1, other_ws])
        listing = await client.get("/api/admin/review-destinations")
    rows = {row["name"]: row for row in listing.json()["destinations"]}
    assert rows["rd-round-trip"]["workspace_filter"] == sorted([1, other_ws])


# ---------------------------------------------------------------------------
# AgentReview workspace_id is populated from request.state on POST
# ---------------------------------------------------------------------------


def test_agent_review_workspace_id_default() -> None:
    """A row inserted with no workspace_id sees the server default of 1."""
    factory = _factory()
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = AgentReview(
            run_id=None,
            period_start=now - datetime.timedelta(hours=1),
            period_end=now,
            severity="ok",
            summary_md="No anomalies in the window.",
            payload_json=None,
            delivered_to_json=None,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert int(row.workspace_id) == 1
