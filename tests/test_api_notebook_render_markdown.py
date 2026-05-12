"""Tests for ``POST /api/notebooks/render-markdown`` (Sprint 66.6)."""

from __future__ import annotations

import httpx


async def test_render_markdown_basic(admin_client: httpx.AsyncClient) -> None:
    """Plain markdown returns a HTML body containing the heading + paragraph."""
    resp = await admin_client.post(
        "/api/notebooks/render-markdown",
        json={"source": "# Hello\n\nworld"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "<h1>" in body["html"]
    assert "Hello" in body["html"]
    assert "world" in body["html"]


async def test_render_markdown_escapes_script(
    admin_client: httpx.AsyncClient,
) -> None:
    """Embedded ``<script>`` tags are escaped — html=False in the parser."""
    resp = await admin_client.post(
        "/api/notebooks/render-markdown",
        json={"source": "<script>alert(1)</script>"},
    )
    assert resp.status_code == 200
    html = resp.json()["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


async def test_render_markdown_empty(
    admin_client: httpx.AsyncClient,
) -> None:
    """Empty source → empty HTML."""
    resp = await admin_client.post(
        "/api/notebooks/render-markdown",
        json={"source": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["html"] == ""


async def test_render_markdown_bad_input(
    admin_client: httpx.AsyncClient,
) -> None:
    """Non-string source → 422."""
    resp = await admin_client.post(
        "/api/notebooks/render-markdown",
        json={"source": 42},
    )
    assert resp.status_code == 422


async def test_render_markdown_non_admin_accessible(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Phase 70: any authenticated user can render markdown."""
    resp = await non_admin_client.post(
        "/api/notebooks/render-markdown",
        json={"source": "x"},
    )
    assert resp.status_code == 200
