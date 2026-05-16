"""Smoke tests for the ``/help`` page (Phase 81.L)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_help_page_renders_for_authenticated_user(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/help`` returns 200 + key section headings."""
    res = await admin_client.get("/help")
    assert res.status_code == 200
    body = res.text
    assert "Help &amp; reference" in body or "Help & reference" in body
    assert "Keyboard shortcuts" in body
    assert "Hidden features" in body
    assert "Glossary" in body


@pytest.mark.asyncio
async def test_help_page_redirects_anonymous_user(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous request to ``/help`` is redirected to the login page."""
    res = await anonymous_client.get("/help", follow_redirects=False)
    assert res.status_code == 303
    assert "/auth/login" in res.headers["location"]
