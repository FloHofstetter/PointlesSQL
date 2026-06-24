"""``GET /embed/semantic_search/{table_fqn}`` — embeddable result iframe.

Mirrors :file:`pointlessql/api/saved_views_routes.py:page_view_embed`:
minimal-chrome HTML page that an outside doc can ``<iframe>`` to
show a frozen semantic-search query.  Authentication still applies —
the JSON fetch carries the session cookie via ``credentials:
'same-origin'``.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._embed_headers import allow_framing
from pointlessql.api.dependencies import current_workspace_id, get_templates, get_user
from pointlessql.db import get_session_factory
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.vector import VectorIndex
from pointlessql.pql._parsing import parse_full_name

router = APIRouter(tags=["sql", "vector-search"])


@router.get("/embed/semantic_search/{table_fqn}", response_class=HTMLResponse)
async def embed_semantic_search(
    request: Request,
    table_fqn: str,
    column: str = Query(..., description="Indexed text column."),
    q: str = Query(..., min_length=1, description="Free-text query string."),
    k: int = Query(10, ge=1, le=200, description="Top-K hits."),
) -> HTMLResponse:
    """Render the embeddable iframe page for a vector-search query.

    Args:
        request: Incoming FastAPI request.
        table_fqn: 3-part UC FQN; ``urlencode``-decoded by FastAPI.
        column: Indexed text column.
        q: Free-text query.
        k: Top-K.

    Returns:
        HTML page that JS-fetches ``/api/sql/vector_search`` on load
        and renders the results inline.

    Raises:
        ResourceNotFoundError: When no index exists for the requested
            ``(table, column)`` in the caller's workspace.
    """
    catalog, schema, table_name = parse_full_name(table_fqn)
    get_user(request)
    workspace_id = current_workspace_id(request)
    session_factory = get_session_factory()
    with session_factory() as session:
        exists = (
            session.query(VectorIndex)
            .filter_by(
                workspace_id=workspace_id,
                catalog=catalog,
                schema=schema,
                table=table_name,
                column=column,
            )
            .one_or_none()
        )
    if exists is None:
        raise ResourceNotFoundError("vector index not found")
    embed_data = {
        "table": table_fqn,
        "catalog": catalog,
        "schema": schema,
        "table_name": table_name,
        "column": column,
        "query": q,
        "top_k": k,
    }
    response = get_templates(request).TemplateResponse(
        request,
        "pages/semantic_search_embed.html",
        {"embed_data": embed_data, "table_fqn": table_fqn, "embed": True},
    )
    return allow_framing(response)
