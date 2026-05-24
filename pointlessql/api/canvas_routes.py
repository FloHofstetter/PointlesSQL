"""Dataflow canvas routes.

* ``GET /canvas`` — HTML editor page.
* ``POST /api/canvas/compile`` — translate a node list to PQL.

The canvas is intentionally not persisted the page
keeps state in ``localStorage`` so the user can iterate without a
DB schema commitment ahead of the 85.2 decision gate.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates, require_user
from pointlessql.services.canvas import SUPPORTED_NODE_KINDS, compile_nodes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["canvas"])


@router.get("/canvas", response_class=HTMLResponse)
async def page_canvas(request: Request) -> HTMLResponse:
    """Render the dataflow canvas page.

    Args:
        request: Incoming request.

    Returns:
        HTML page (login-gated).
    """
    require_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/canvas.html",
        {
            "active_page": "canvas",
            "supported_node_kinds": list(SUPPORTED_NODE_KINDS),
        },
    )


@router.post("/api/canvas/compile")
async def api_canvas_compile(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Translate a list of canvas nodes into a PQL script.

    Args:
        request: Incoming request.
        body: ``{"nodes": [{kind, config}, ...]}``.

    Returns:
        ``{"code": "...", "errors": [...]}``.  ``code`` is empty
        when ``errors`` is non-empty.
    """
    require_user(request)
    nodes = (body or {}).get("nodes") or []
    if not isinstance(nodes, list):
        return {"code": "", "errors": ["nodes must be a list."]}
    typed: list[dict[str, Any]] = []
    for n in nodes:  # type: ignore[reportUnknownVariableType]
        if isinstance(n, dict):
            typed.append(n)  # type: ignore[reportUnknownArgumentType]
    code, errors = await asyncio.to_thread(compile_nodes, typed)
    return {"code": code, "errors": errors}
