"""Tests for the ``GET /api/audit/cdf-events`` endpoint."""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import CdfTailEvent, CdfTailSubscription


def _authed_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed_subscription(table: str, *, is_active: bool = True) -> int:
    factory = app.state.session_factory
    with factory() as session:
        sub = CdfTailSubscription(
            workspace_id=1,
            table_full_name=table,
            row_id_column="id",
            producer_label=f"cdf-tail:{table}",
            is_active=is_active,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        return sub.id


def _seed_event(sub_id: int, table: str, *, version: int, row_id: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        ev = CdfTailEvent(
            workspace_id=1,
            subscription_id=sub_id,
            table_full_name=table,
            delta_version=version,
            row_id=row_id,
            change_type="insert",
            producer_label=f"cdf-tail:{table}",
            commit_timestamp=datetime.datetime.now(datetime.UTC),
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(ev)
        session.commit()


class TestAuditCdfEvents:
    """Plugin/agent-facing read endpoint for CDF tail captures."""

    @pytest.mark.asyncio
    async def test_returns_subscription_and_events(self) -> None:
        full_name = "demo.silver.tracked"
        sub_id = _seed_subscription(full_name)
        _seed_event(sub_id, full_name, version=0, row_id="42")
        _seed_event(sub_id, full_name, version=1, row_id="43")
        async with _authed_client() as c:
            resp = await c.get("/api/audit/cdf-events", params={"table": full_name})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["table"] == full_name
        assert body["subscription"]["table_full_name"] == full_name
        assert body["subscription"]["row_id_column"] == "id"
        assert len(body["events"]) == 2
        assert {e["row_id"] for e in body["events"]} == {"42", "43"}

    @pytest.mark.asyncio
    async def test_returns_null_subscription_when_none_registered(self) -> None:
        async with _authed_client() as c:
            resp = await c.get(
                "/api/audit/cdf-events",
                params={"table": "demo.silver.nada"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["subscription"] is None
        assert body["events"] == []

    @pytest.mark.asyncio
    async def test_subscriptions_listing(self) -> None:
        _seed_subscription("demo.silver.tracked_a")
        _seed_subscription("demo.silver.paused_b", is_active=False)
        async with _authed_client() as c:
            resp = await c.get("/api/audit/cdf-subscriptions")
        assert resp.status_code == 200
        body = resp.json()
        names = {s["table_full_name"] for s in body["subscriptions"]}
        assert names == {"demo.silver.tracked_a", "demo.silver.paused_b"}

        async with _authed_client() as c:
            resp = await c.get("/api/audit/cdf-subscriptions", params={"only_active": "true"})
        assert resp.status_code == 200
        body = resp.json()
        names = {s["table_full_name"] for s in body["subscriptions"]}
        assert names == {"demo.silver.tracked_a"}

    @pytest.mark.asyncio
    async def test_limit_clamps_to_max_500(self) -> None:
        async with _authed_client() as c:
            resp = await c.get(
                "/api/audit/cdf-events",
                params={"table": "demo.silver.x", "limit": 9999},
            )
        # FastAPI Query(le=500) returns 422 for over-cap requests.
        assert resp.status_code == 422
