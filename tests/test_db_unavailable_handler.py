"""A metadata-DB operational failure is a retryable 503, not a 500.

When the metadata DB is unreachable the request used to fall through to
the generic 500 internal_error handler, so monitors could not tell an
outage from a bug — and str(exc) (which carries the DSN) risked leaking.
This pins the dedicated OperationalError handler: 503, a stable code, and
no DSN in the body.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient

_SECRET_DSN = "postgresql://user:SUPERSECRETPW@db:5432/app"


@pytest.fixture(autouse=True)
def _failing_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the catalog list raise an OperationalError carrying a DSN."""
    err = OperationalError("SELECT 1", {}, Exception(f"could not connect: {_SECRET_DSN}"))
    client = MagicMock(spec=UnityCatalogClient)
    client.list_catalogs = AsyncMock(side_effect=err)
    app.state.uc_client = client
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_operational_error_is_classified_503() -> None:
    """The handler returns 503 + database_unavailable without leaking the DSN."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        resp = await client.get("/api/catalogs")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "database_unavailable"
    assert body["status"] == 503
    assert _SECRET_DSN not in resp.text
    assert "SUPERSECRETPW" not in resp.text
