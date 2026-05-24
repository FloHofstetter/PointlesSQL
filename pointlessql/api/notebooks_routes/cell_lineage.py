"""Cell-level lineage badge route.

Returns the list of Delta-write events the audit trail has captured
for a single notebook cell so the editor's cell header can paint
"<table>" chips next to the run pill.  The query is read-only and
honours the same workspace gate the rest of the notebook routes use
(any authenticated user; tenant scope comes from the cookie user).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.config import Settings
from pointlessql.services.notebook import _doc as notebook_doc_service
from pointlessql.services.notebook import cell_lineage as cell_lineage_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


@router.get("/api/notebooks/cell/lineage/bulk")
async def api_cell_lineage_bulk(
    request: Request, path: str = Query(..., min_length=1)
) -> JSONResponse:
    """Return ``{content_hash: [badge, ...]}`` for every cell in a notebook.

    The cell-header chip strip in the editor needs N badges in a
    single call; the per-cell endpoint stays around for deep-link
    usage but is N+1 for the editor.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.

    Returns:
        JSON ``{"path": ..., "badges": {<content_hash>: [...]}}`` —
        cells with no write history are omitted from ``badges``; the
        frontend defaults to an empty list per row.
    """
    require_user(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    factory = request.app.state.session_factory
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges_bulk(
            session,
            file_path=relative,
        )
    return JSONResponse(
        {
            "path": relative,
            "badges": badges,
        }
    )


@router.get("/api/notebooks/cell/lineage")
async def api_cell_lineage(
    request: Request,
    path: str = Query(..., min_length=1),
    content_hash: str = Query(..., min_length=1),
) -> JSONResponse:
    """Return write-op badges for one cell.

    Args:
        request: Incoming request; any authenticated user.
        path: Relative notebook path under ``notebooks_dir``.
        content_hash: ``sha256(source)[:16]`` of the cell source.

    Returns:
        JSON ``{"path": ..., "content_hash": ..., "badges": [...]}``.
        ``badges`` is an empty list when the cell has never written
        anything in an agent-run context.
    """
    require_user(request)
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(notebooks_dir, path, must_exist=True)
    relative = str(absolute.relative_to(notebooks_dir))
    factory = request.app.state.session_factory
    with factory() as session:
        badges = cell_lineage_service.list_cell_lineage_badges(
            session,
            file_path=relative,
            content_hash=content_hash,
        )
    return JSONResponse(
        {
            "path": relative,
            "content_hash": content_hash,
            "badges": badges,
        }
    )
