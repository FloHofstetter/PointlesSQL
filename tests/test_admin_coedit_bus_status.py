"""operator diagnostics for the cross-worker co-edit bus."""

from __future__ import annotations

import httpx
import pytest


class TestCoeditBusStatusEndpoint:
    """GET /api/admin/coedit-bus/status."""

    @pytest.mark.asyncio
    async def test_returns_disabled_when_bus_not_bound(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        """Default single-worker install reports ``enabled: false``."""
        resp = await admin_client.get("/api/admin/coedit-bus/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"enabled": False}

    @pytest.mark.asyncio
    async def test_non_admin_is_forbidden(self, non_admin_client: httpx.AsyncClient) -> None:
        """Non-admin members hit ``require_admin``."""
        resp = await non_admin_client.get("/api/admin/coedit-bus/status")
        assert resp.status_code == 403
