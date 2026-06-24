"""/readyz exercises the DB and soyuz so orchestrators see real readiness.

/healthz is static liveness; /readyz must return 503 (naming the failed
component) when the metadata DB or soyuz-catalog is unreachable, and 200
only when both answer.  It is unauthenticated so a probe needs no session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api import health_routes
from pointlessql.api.main import app


@pytest.mark.asyncio
async def test_readyz_ok_when_db_and_soyuz_healthy(
    anonymous_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both dependencies healthy → 200 ready, no auth required."""
    monkeypatch.setattr(health_routes, "probe_soyuz", AsyncMock(return_value="ok"))
    res = await anonymous_client.get("/readyz")
    assert res.status_code == 200
    assert res.json() == {"status": "ready", "db": "ok", "soyuz": "ok"}


@pytest.mark.asyncio
async def test_readyz_503_when_soyuz_down(
    anonymous_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreachable soyuz yields 503 naming soyuz."""
    monkeypatch.setattr(health_routes, "probe_soyuz", AsyncMock(return_value="down"))
    res = await anonymous_client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["soyuz"] == "down"


@pytest.mark.asyncio
async def test_readyz_503_when_db_down(
    anonymous_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing DB query yields 503 naming the db."""
    monkeypatch.setattr(health_routes, "probe_soyuz", AsyncMock(return_value="ok"))

    def _boom() -> object:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(app.state, "session_factory", _boom)
    res = await anonymous_client.get("/readyz")
    assert res.status_code == 503
    assert res.json()["db"] == "down"
