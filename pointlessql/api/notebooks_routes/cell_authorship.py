"""Per-cell authorship routes (Phase 101).

Exposes the read surface the editor's cell-header chip + the agent-
profile page consume.  Writes happen via the save-path reconciler +
the Phase-96 AI-assistant acceptance path — not via REST — so no
``POST`` is exposed here today.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import ValidationError
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


@router.get("/api/agents/{agent_id}/authored-cells")
async def api_agent_authored_cells(
    request: Request,
    agent_id: int,
    limit: int = Query(100, ge=1, le=500),
) -> JSONResponse:
    """Return cells minted by one agent, newest first.

    Args:
        request: Incoming request; any authenticated user.
        agent_id: ``agents.id``.
        limit: Newest-N cap (1–500, default 100).

    Returns:
        JSON ``{"agent_id": ..., "cells": [...]}``.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        cells = cell_authorship_service.list_authored_by_agent(
            session, agent_id=agent_id, limit=limit
        )
    return JSONResponse({"agent_id": agent_id, "cells": cells})
