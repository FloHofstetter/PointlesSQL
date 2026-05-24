"""Notebook replay / scenario-mode routes (Phase 103)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
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
from pointlessql.services.notebook import replay as notebook_replay_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebooks"])


def _resolve_notebook_uuid(request: Request, path: str) -> str:
    settings: Settings = request.app.state.settings
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    absolute = notebook_doc_service.resolve_py_notebook_path(
        notebooks_dir, path, must_exist=True
    )
    relative = str(absolute.relative_to(notebooks_dir))
    return get_or_create_notebook_uuid(request, relative)


@router.post("/api/notebooks/replay", status_code=201)
async def api_start_replay(
    request: Request, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    """Insert a fresh replay row in ``pending`` state.

    Body keys:
        path: Relative notebook path.
        base_revision_uuid: Phase-97 revision the replay forks from.
        branch_name: Optional Phase-102 branch the replay's writes
            target.
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    path = body.get("path")
    base_rev = body.get("base_revision_uuid")
    branch_name = body.get("branch_name")
    if not isinstance(path, str) or not isinstance(base_rev, str):
        raise ValidationError(
            "body.path and body.base_revision_uuid must be strings"
        )
    if branch_name is not None and not isinstance(branch_name, str):
        raise ValidationError("body.branch_name must be a string or null")
    notebook_id = _resolve_notebook_uuid(request, path)
    actor_id: int | None = None
    try:
        actor_id = (
            request.state.user.get("id") if request.state.user else None
        )
    except AttributeError:
        actor_id = None
    factory = request.app.state.session_factory
    with factory() as session:
        row = notebook_replay_service.start_replay(
            session,
            notebook_id=notebook_id,
            base_revision_uuid=base_rev,
            branch_name=branch_name,
            triggered_by_user_id=actor_id,
        )
        envelope = notebook_replay_service.get_replay(
            session, replay_uuid=row.replay_uuid
        )
        session.commit()
    assert envelope is not None
    return JSONResponse(envelope, status_code=201)


@router.post("/api/notebooks/replay/{replay_uuid}/finish")
async def api_record_replay_finished(
    request: Request,
    replay_uuid: str,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Record a terminal status + replayed outputs.

    Body keys:
        status: ``"ok"`` | ``"error"`` | ``"cancelled"``.
        outputs: List of output rows (Phase-96 load shape).
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    status = body.get("status")
    outputs = body.get("outputs", [])
    if not isinstance(status, str):
        raise ValidationError("body.status must be a string")
    if not isinstance(outputs, list):
        raise ValidationError("body.outputs must be a list")
    factory = request.app.state.session_factory
    with factory() as session:
        notebook_replay_service.record_finished(
            session,
            replay_uuid=replay_uuid,
            status=status,
            outputs=outputs,
        )
        envelope = notebook_replay_service.get_replay(
            session, replay_uuid=replay_uuid
        )
        session.commit()
    return JSONResponse(envelope or {})


@router.get("/api/notebooks/replay/{replay_uuid}")
async def api_get_replay(request: Request, replay_uuid: str) -> JSONResponse:
    """Return one replay envelope including outputs."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_replay_service.get_replay(
            session, replay_uuid=replay_uuid
        )
    if envelope is None:
        raise ValidationError(f"replay {replay_uuid!r} not found")
    return JSONResponse(envelope)


@router.get("/api/notebooks/replay/{replay_uuid}/diff")
async def api_replay_diff(
    request: Request, replay_uuid: str
) -> JSONResponse:
    """Return the cell-by-cell side-by-side diff envelope."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = notebook_replay_service.compute_replay_diff(
            session, replay_uuid=replay_uuid
        )
    return JSONResponse(envelope)


@router.get("/api/notebooks/replays")
async def api_list_replays(
    request: Request,
    path: str = Query(..., min_length=1),
    paging: PaginationParams = Depends(pagination),
) -> JSONResponse:
    """List replays for one notebook, newest first."""
    require_user(request)
    notebook_id = _resolve_notebook_uuid(request, path)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = notebook_replay_service.list_replays(
            session,
            notebook_id=notebook_id,
            limit=paging.limit,
            offset=paging.offset,
        )
    return JSONResponse(
        {"path": path, "notebook_id": notebook_id, "replays": rows}
    )
