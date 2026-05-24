"""Phase 121.6 Item D — ``render_page_with_fallback`` helper."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pointlessql.api.dependencies import render_page_with_fallback
from pointlessql.exceptions import CatalogUnavailableError


@pytest.mark.asyncio
async def test_render_page_success_path() -> None:
    """Successful fetch → context has data + error=None."""
    request = MagicMock()
    templates = MagicMock()
    request.app.state.templates = templates

    captured: dict[str, object] = {}

    def fake_template_response(req, name, ctx):
        captured["request"] = req
        captured["name"] = name
        captured["context"] = ctx
        return "rendered"

    templates.TemplateResponse = fake_template_response

    async def fetch() -> list[int]:
        return [1, 2, 3]

    result = await render_page_with_fallback(
        request,
        "pages/x.html",
        fetch,
        context_key="items",
    )
    assert result == "rendered"
    assert captured["name"] == "pages/x.html"
    assert captured["context"] == {"items": [1, 2, 3], "error": None}


@pytest.mark.asyncio
async def test_render_page_catalog_unavailable_renders_banner() -> None:
    """``CatalogUnavailableError`` → empty data + error=exc.detail."""
    request = MagicMock()
    templates = MagicMock()
    request.app.state.templates = templates

    captured: dict[str, object] = {}

    def fake_template_response(req, name, ctx):
        captured["context"] = ctx
        return "rendered"

    templates.TemplateResponse = fake_template_response

    async def fetch():
        raise CatalogUnavailableError("soyuz is down")

    result = await render_page_with_fallback(
        request,
        "pages/x.html",
        fetch,
        context_key="thing",
    )
    assert result == "rendered"
    ctx = captured["context"]
    assert ctx["thing"] == []
    assert ctx["error"] == "soyuz is down"


@pytest.mark.asyncio
async def test_render_page_extra_context_is_merged() -> None:
    """``extra_context`` keys land in the template namespace alongside item/error."""
    request = MagicMock()
    templates = MagicMock()
    request.app.state.templates = templates

    captured: dict[str, object] = {}

    def fake_template_response(req, name, ctx):
        captured["context"] = ctx
        return "rendered"

    templates.TemplateResponse = fake_template_response

    async def fetch() -> dict[str, str]:
        return {"name": "foo"}

    await render_page_with_fallback(
        request,
        "pages/x.html",
        fetch,
        context_key="obj",
        extra_context={"active_page": "p", "list_page": True},
    )
    ctx = captured["context"]
    assert ctx == {
        "obj": {"name": "foo"},
        "error": None,
        "active_page": "p",
        "list_page": True,
    }


@pytest.mark.asyncio
async def test_render_page_non_catalog_exception_propagates() -> None:
    """Non-CatalogUnavailableError exceptions are NOT swallowed by the helper."""
    request = MagicMock()
    templates = MagicMock()
    request.app.state.templates = templates

    async def fetch():
        raise RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        await render_page_with_fallback(
            request,
            "pages/x.html",
            fetch,
            context_key="items",
        )
