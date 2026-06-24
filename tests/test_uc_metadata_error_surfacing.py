"""list_tables / list_volumes surface soyuz outages instead of masking them.

The raw soyuz GETs collapsed every non-200 to an empty list, so a 5xx or
timeout rendered a schema as "no tables" — indistinguishable from a
genuinely empty schema.  These tests pin that 404 still means empty while
a 5xx raises CatalogUnavailableError via @wrap_catalog_errors.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.services.unitycatalog import UnityCatalogClient


class _FakeHttp:
    def __init__(self, resp: httpx.Response) -> None:
        self._resp = resp

    async def get(self, url: str, params: Any = None) -> httpx.Response:
        return self._resp


class _FakeClient:
    def __init__(self, resp: httpx.Response) -> None:
        self._resp = resp

    def get_async_httpx_client(self) -> _FakeHttp:
        return _FakeHttp(self._resp)


def _uc(status: int, body: dict[str, Any] | None = None) -> UnityCatalogClient:
    resp = httpx.Response(status, json=body or {}, request=httpx.Request("GET", "http://x"))
    return UnityCatalogClient(_FakeClient(resp))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_list_tables_5xx_raises_unavailable() -> None:
    """A 500 from soyuz surfaces as CatalogUnavailableError."""
    with pytest.raises(CatalogUnavailableError):
        await _uc(500).list_tables("cat", "sch")


@pytest.mark.asyncio
async def test_list_tables_404_is_empty() -> None:
    """A 404 still means a genuinely empty/absent listing."""
    assert await _uc(404).list_tables("cat", "sch") == []


@pytest.mark.asyncio
async def test_list_tables_200_returns_rows() -> None:
    """A 200 returns the parsed table list unchanged."""
    rows = await _uc(200, {"tables": [{"name": "t1"}]}).list_tables("cat", "sch")
    assert rows == [{"name": "t1"}]


@pytest.mark.asyncio
async def test_list_volumes_5xx_raises_unavailable() -> None:
    """A 500 from the volumes endpoint surfaces as CatalogUnavailableError."""
    with pytest.raises(CatalogUnavailableError):
        await _uc(500).list_volumes("cat", "sch")


@pytest.mark.asyncio
async def test_list_volumes_404_is_empty() -> None:
    """A 404 from the volumes endpoint means empty."""
    assert await _uc(404).list_volumes("cat", "sch") == []
