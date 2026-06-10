"""Sequence-proposal REST routes.

* ``POST /api/notebook/chat/{chat_session_id}/propose-sequence`` —
  insert a multi-cell proposal.
* ``GET  /api/notebook/chat/sequences/{proposal_id}`` — fetch one
  envelope.
* ``POST /api/notebook/chat/sequences/{proposal_id}/accept`` —
  flip to ``accepted``.
* ``POST /api/notebook/chat/sequences/{proposal_id}/discard`` —
  flip to ``discarded``.
* ``GET  /api/notebook/chat/{chat_session_id}/sequences/pending`` —
  list pending proposals on a chat session.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models import EditorChatSession
from pointlessql.services.notebook import (
    cell_sequence_proposals as cell_sequence_proposals_service,
)


def _resolve_chat_session_int_id(request: Request, raw: str) -> int:
    """Resolve ``raw`` (integer string or editor_session_id UUID) to int id.

    The route also accepts the matching editor_session_id (UUID7)
    so the hermes-plugin tool can address the session by the same
    id it uses for ``propose-cell``.  Plain integer strings keep
    working for backward compatibility.

    Args:
        request: Incoming request.
        raw: Path-segment value — digits or a 36-char UUID.

    Returns:
        The ``editor_chat_sessions.id`` integer.

    Raises:
        ResourceNotFoundError: When *raw* is neither a parseable
            integer nor a known ``editor_session_id`` UUID.
    """
    if raw.isdigit():
        return int(raw)
    factory = request.app.state.session_factory
    with factory() as session:
        row = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == raw)
            .one_or_none()
        )
    if row is None:
        raise ResourceNotFoundError("notebook chat session not found.")
    return int(row.id)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["notebook-chat"])


@router.post(
    "/api/notebook/chat/{chat_session_id}/propose-sequence",
    status_code=201,
)
async def api_propose_sequence(
    request: Request,
    chat_session_id: str,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Insert a new sequence proposal.

    Body keys:
        prompt: Verbatim user prompt that drove the suggestion.
        cells: Ordered list of cell dicts.
        rationale: Optional narrative.

    ``chat_session_id`` accepts the integer ``editor_chat_sessions.id``
    (original form) or the ``editor_session_id`` UUID7 (symmetry
    with the ``propose-cell`` route the hermes-plugin already uses).
    """
    require_user(request)
    if not isinstance(body, dict):
        raise ValidationError("body must be a JSON object")
    prompt = body.get("prompt")
    cells = body.get("cells")
    rationale = body.get("rationale")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValidationError("body.prompt must be a non-empty string")
    if not isinstance(cells, list):
        raise ValidationError("body.cells must be a list")
    if rationale is not None and not isinstance(rationale, str):
        raise ValidationError("body.rationale must be a string or null")
    int_session_id = _resolve_chat_session_int_id(request, chat_session_id)
    factory = request.app.state.session_factory
    with factory() as session:
        row = cell_sequence_proposals_service.propose_sequence(
            session,
            chat_session_id=int_session_id,
            prompt=prompt,
            cells=cells,
            rationale=rationale,
        )
        envelope = cell_sequence_proposals_service.get_sequence(
            session, proposal_id=row.proposal_id
        )
        session.commit()
    assert envelope is not None
    return JSONResponse(envelope, status_code=201)


@router.get("/api/notebook/chat/sequences/{proposal_id}")
async def api_get_sequence(request: Request, proposal_id: str) -> JSONResponse:
    """Return one sequence proposal envelope."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        envelope = cell_sequence_proposals_service.get_sequence(session, proposal_id=proposal_id)
    if envelope is None:
        raise ValidationError(f"sequence proposal {proposal_id!r} not found")
    return JSONResponse(envelope)


@router.post("/api/notebook/chat/sequences/{proposal_id}/accept")
async def api_accept_sequence(request: Request, proposal_id: str) -> JSONResponse:
    """Flip a sequence proposal to ``accepted``."""
    require_user(request)
    actor_id: int | None = None
    try:
        actor_id = request.state.user.get("id") if request.state.user else None
    except AttributeError:
        actor_id = None
    factory = request.app.state.session_factory
    with factory() as session:
        cell_sequence_proposals_service.accept_sequence(
            session,
            proposal_id=proposal_id,
            accepted_by_user_id=actor_id,
        )
        envelope = cell_sequence_proposals_service.get_sequence(session, proposal_id=proposal_id)
        session.commit()
    return JSONResponse(envelope or {})


@router.post("/api/notebook/chat/sequences/{proposal_id}/discard")
async def api_discard_sequence(request: Request, proposal_id: str) -> JSONResponse:
    """Flip a sequence proposal to ``discarded``."""
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        cell_sequence_proposals_service.discard_sequence(session, proposal_id=proposal_id)
        envelope = cell_sequence_proposals_service.get_sequence(session, proposal_id=proposal_id)
        session.commit()
    return JSONResponse(envelope or {})


@router.get("/api/notebook/chat/{chat_session_id}/sequences/pending")
async def api_list_pending_sequences(request: Request, chat_session_id: str) -> JSONResponse:
    """List pending sequence proposals for a chat session."""
    require_user(request)
    int_session_id = _resolve_chat_session_int_id(request, chat_session_id)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = cell_sequence_proposals_service.list_pending_for_session(
            session, chat_session_id=int_session_id
        )
    return JSONResponse({"proposals": rows})
