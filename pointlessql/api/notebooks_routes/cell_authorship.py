"""Per-cell authorship routes.

Exposes the read surface the editor's cell-header chip + the agent-
profile page consume.  Writes happen via the save-path reconciler +
the Phase-96 AI-assistant acceptance path — not via REST — so no
``POST`` is exposed here today.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import (
    PaginationParams,
    pagination,
    require_user,
)
from pointlessql.api.notebooks_routes._shared import get_or_create_notebook_uuid
from pointlessql.config import Settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import cell_authorship as cell_authorship_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/cell/attribution")
async def api_cell_attribution(
    request: Request,
    cell_uuid: str = Query(..., min_length=36, max_length=36),
) -> JSONResponse:
    """Return the attribution envelope for one cell.

    Args:
        request: Incoming request; any authenticated user.
        cell_uuid: ``NotebookCellIdentity.id``.

    Returns:
        JSON ``{cell_uuid, first_author, last_modifier, created_at,
        last_modified_at}``.

    Raises:
        ValidationError: When no authorship row exists for the cell.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = cell_authorship_service.get_attribution(
            session, cell_uuid=cell_uuid
        )
    if envelope is None:
        raise ValidationError(
            f"no authorship row for cell {cell_uuid!r}"
        )
    return JSONResponse(envelope)


@router.get("/api/notebooks/attribution/bulk")
async def api_notebook_attribution_bulk(
    request: Request,
    path: str = Query(..., min_length=1),
) -> JSONResponse:
    """Return ``{cell_uuid: envelope}`` for every cell of one notebook.

    The editor calls this once on page-mount + after every save so
    the per-cell author chip can render without N HTTP round-trips.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        JSON ``{path, notebook_id, attributions: {cell_uuid: ...}}``.
    """
    require_user(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    notebook_id = get_or_create_notebook_uuid(request, relative)
    factory = request.app.state.session_factory
    with factory() as session:
        attributions = cell_authorship_service.list_for_notebook(
            session, notebook_id=notebook_id
        )
    return JSONResponse(
        {
            "path": relative,
            "notebook_id": notebook_id,
            "attributions": attributions,
        }
    )


@router.get("/api/agents/{agent_id}/authored-cells")
async def api_agent_authored_cells(
    request: Request,
    agent_id: int,
    paging: PaginationParams = Depends(pagination),
) -> JSONResponse:
    """Return cells minted by one agent, newest first.

    Args:
        request: Incoming request; any authenticated user.
        agent_id: ``agents.id``.
        paging: Shared offset+limit pair (default page size 100, max 1000).

    Returns:
        JSON ``{"agent_id": ..., "cells": [...]}``.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        cells = cell_authorship_service.list_authored_by_agent(
            session,
            agent_id=agent_id,
            limit=paging.limit,
            offset=paging.offset,
        )
    return JSONResponse({"agent_id": agent_id, "cells": cells})
