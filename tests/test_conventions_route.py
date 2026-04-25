"""Tests for the Sprint 13.7.3 ``GET /api/conventions`` route.

Read-only public surface that lets the
``hermes-plugin-pointlessql`` ``pql_conventions`` tool dump the
Medallion contract straight into an LLM system prompt.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.main import app


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


@pytest.mark.asyncio
async def test_conventions_returns_yaml_and_doc_excerpt() -> None:
    async with _admin_client() as client:
        response = await client.get("/api/conventions")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "yaml" in payload
    assert "doc_markdown" in payload
    yaml_block = payload["yaml"]
    # ConventionsConfig.model_dump() always carries the layer
    # contract; we don't assert exact field names because they
    # may evolve, only the shape that any caller relies on.
    assert isinstance(yaml_block, dict)
    assert yaml_block, "model_dump() must not return an empty dict"


@pytest.mark.asyncio
async def test_conventions_unauthenticated_redirects_or_401() -> None:
    """The conventions endpoint sits under ``/api/`` so the auth
    middleware applies the same 401 behaviour as the other API
    routes (no session cookie + no Bearer = 401)."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get("/api/conventions")
    assert response.status_code == 401
