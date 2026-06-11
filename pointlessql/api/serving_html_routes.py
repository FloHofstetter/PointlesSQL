"""Model-serving HTML page — the endpoint cockpit at ``/serving``.

One HTML route for any signed-in user; the JSON lifecycle +
invocation surface it drives lives in
:mod:`pointlessql.api.serving_routes`.  The page receives the active
workspace's endpoint rows server-side (projected to the exact shape
``GET /api/serving-endpoints`` answers) so the table paints without
a fetch round-trip and the Alpine factory can swap in refreshed
lists without reshaping.

NOTE: this router is intentionally **not registered** yet.  The
navigation integration wires it into
``pointlessql/api/_bootstrap/_routers.py`` next to the
``serving_routes`` JSON router (``app.include_router(...)``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import current_workspace_id, get_templates
from pointlessql.models.serving import ServingEndpoint
from pointlessql.services import model_serving as serving_service

router = APIRouter(tags=["serving-html"])


def _serialize_endpoint(row: ServingEndpoint) -> dict[str, Any]:
    """Project an endpoint row to the JSON-list shape.

    Mirrors the ``GET /api/serving-endpoints`` projection so the page
    factory's seed data and its refresh fetches stay interchangeable.

    Args:
        row: Detached endpoint row.

    Returns:
        A JSON-safe dict of the endpoint's list-view fields.
    """
    return {
        "id": row.id,
        "name": row.name,
        "model_name": row.model_name,
        "model_version": row.model_version,
        "state": row.state,
        "last_error": row.last_error,
        "created_by": row.created_by,
        "invocation_count": row.invocation_count,
        "last_invoked_at": row.last_invoked_at.isoformat() if row.last_invoked_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/serving", response_class=HTMLResponse)
async def serving_page(request: Request):
    """Render the model-serving cockpit (endpoint table + try-it drawer)."""
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    rows = serving_service.list_endpoints(factory, workspace_id=workspace_id)
    return get_templates(request).TemplateResponse(
        request,
        "pages/serving.html",
        {
            "active_page": "serving",
            "endpoints": [_serialize_endpoint(row) for row in rows],
        },
    )
