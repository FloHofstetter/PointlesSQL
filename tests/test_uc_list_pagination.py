"""UC list facades drain every page, not just soyuz's first.

list_tables / list_volumes previously read a single page, so a large
schema was silently truncated.  These tests pin that the facade follows
next_page_token to the end and forwards the cursor each call.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.services.unitycatalog import UnityCatalogClient


class _PagedHttp:
    """A fake async httpx client returning two pages keyed on page_token."""

    def __init__(self, key: str) -> None:
        self._key = key
        self.tokens_seen: list[str | None] = []

    async def get(self, url: str, params: Any = None) -> httpx.Response:
        params = params or {}
        token = params.get("page_token")
        self.tokens_seen.append(token)
        req = httpx.Request("GET", "http://x")
        if not token:
            return httpx.Response(
                200, json={self._key: [{"name": "a"}], "next_page_token": "p2"}, request=req
            )
        return httpx.Response(200, json={self._key: [{"name": "b"}]}, request=req)


class _PagedClient:
    def __init__(self, http: _PagedHttp) -> None:
        self._http = http

    def get_async_httpx_client(self) -> _PagedHttp:
        return self._http


@pytest.mark.asyncio
async def test_list_tables_drains_all_pages() -> None:
    """Tables from both pages are concatenated; the cursor is forwarded."""
    http = _PagedHttp("tables")
    uc = UnityCatalogClient(_PagedClient(http))  # type: ignore[arg-type]
    rows = await uc.list_tables("cat", "sch")
    assert rows == [{"name": "a"}, {"name": "b"}]
    assert http.tokens_seen == [None, "p2"]


@pytest.mark.asyncio
async def test_list_volumes_drains_all_pages() -> None:
    """Volumes from both pages are concatenated."""
    http = _PagedHttp("volumes")
    uc = UnityCatalogClient(_PagedClient(http))  # type: ignore[arg-type]
    rows = await uc.list_volumes("cat", "sch")
    assert rows == [{"name": "a"}, {"name": "b"}]
    assert http.tokens_seen == [None, "p2"]
