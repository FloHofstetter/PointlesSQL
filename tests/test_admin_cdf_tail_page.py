"""Tests for the Phase 40.6 admin CDF subscriptions HTML page."""

from __future__ import annotations

import datetime

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import CdfTailSubscription


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


def _seed(table: str, *, is_active: bool = True, last_error: str | None = None) -> int:
    """Insert one CdfTailSubscription and return its id."""
    factory = app.state.session_factory
    with factory() as session:
        sub = CdfTailSubscription(
            workspace_id=1,
            table_full_name=table,
            row_id_column="id",
            producer_label=f"cdf-tail:{table}",
            is_active=is_active,
            last_error=last_error,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(sub)
        session.commit()
        return sub.id


class TestAdminCdfTailPage:
    """``GET /admin/cdf-subscriptions`` rendering + filter behaviour."""

    @pytest.mark.asyncio
    async def test_renders_subscription_list(self) -> None:
        sub_id = _seed("demo.silver.orders")
        async with _admin_client() as c:
            resp = await c.get("/admin/cdf-subscriptions")
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert "demo.silver.orders" in body
        assert f'/api/admin/cdf-subscriptions/{sub_id}/toggle' in body
        # Healthy install -> green badge, no error chip.
        assert "all healthy" in body

    @pytest.mark.asyncio
    async def test_filters_by_table_substring(self) -> None:
        _seed("demo.silver.orders")
        _seed("demo.bronze.events")
        async with _admin_client() as c:
            resp = await c.get(
                "/admin/cdf-subscriptions",
                params={"table_fqn_like": "silver"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert "demo.silver.orders" in body
        assert "demo.bronze.events" not in body

    @pytest.mark.asyncio
    async def test_only_active_filter_drops_paused(self) -> None:
        _seed("demo.silver.active_one", is_active=True)
        _seed("demo.silver.paused_one", is_active=False)
        async with _admin_client() as c:
            resp = await c.get(
                "/admin/cdf-subscriptions",
                params={"only_active": "true"},
            )
        assert resp.status_code == 200
        body = resp.text
        assert "demo.silver.active_one" in body
        assert "demo.silver.paused_one" not in body

    @pytest.mark.asyncio
    async def test_error_badge_surfaces_last_error_count(self) -> None:
        _seed("demo.silver.broken", last_error="storage_location not reachable")
        async with _admin_client() as c:
            resp = await c.get("/admin/cdf-subscriptions")
        assert resp.status_code == 200
        body = resp.text
        assert "with last_error" in body
        assert "storage_location not reachable" in body
