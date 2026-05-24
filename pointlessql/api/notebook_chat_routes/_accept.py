"""``POST /api/notebook/chat/proposals/{id}/{accept,discard}``.

Lifecycle endpoints for :class:`NotebookCellProposal` rows of
``action='propose'`` and ``action='fix'``.  ``explain`` proposals
are created at status ``accepted`` directly so they have no accept
endpoint — but discard still works (lets the user dismiss a stale
explanation).

Accept returns the full payload the frontend needs to apply the
change to the editor: action, cell_type, source, target_cell_uuid,
position hints, and the chat session's ``agent_run_id`` so the
next ``/api/notebooks/save`` can stamp provenance.

Also exposes ``GET /api/notebook/chat/cell/{cell_uuid}/explanations``
— the per-cell social drawer's Explanations tab reads it.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import ConflictError, ResourceNotFoundError
from pointlessql.models import (
    EditorChatSession,
    NotebookCellProposal,
)
from pointlessql.services.editor_chat import ChatEvent, publish

logger = logging.getLogger(__name__)

router = APIRouter()

_PROPOSAL_TTL_HOURS: int = 24


@router.post("/api/notebook/chat/proposals/{proposal_id}/accept")
async def api_accept_proposal(
    request: Request, proposal_id: str
) -> dict[str, Any]:
    """Mark *proposal_id* accepted; return the payload to apply.

    Args:
        request: Incoming request.  Must be authenticated.
        proposal_id: The UUID returned by the propose / fix route.

    Returns:
        ``{"proposal_id", "action", "cell_type", "new_source",
        "target_cell_uuid", "position_after_cell_uuid",
        "position_at_end", "agent_run_id"}``.  ``cell_type`` is
        ``None`` for fix; ``target_cell_uuid`` is ``None`` for
        propose; ``position_*`` is ignored by the frontend for fix.

    Raises:
        ResourceNotFoundError: When the proposal is unknown.
        ConflictError: When already accepted / discarded / older
            than 24 h.
    """  # noqa: DOC502
    require_user(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(hours=_PROPOSAL_TTL_HOURS)

    with factory() as session:
        proposal = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one_or_none()
        )
        if proposal is None:
            raise ResourceNotFoundError.not_found(what=f"proposal {proposal_id!r}")
        if proposal.action == "explain":
            raise ConflictError(
                "explain proposals are auto-accepted at create-time; "
                "no accept endpoint applies"
            )
        if proposal.status != "pending":
            raise ConflictError(f"proposal already {proposal.status}")
        created_at = proposal.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.UTC)
        if created_at < cutoff:
            proposal.status = "expired"
            proposal.accepted_at = now
            session.commit()
            raise ConflictError(
                "proposal is older than 24 hours and cannot be "
                "accepted; ask the chat to redraft."
            )
        chat_session = session.get(EditorChatSession, proposal.chat_session_id)
        if chat_session is None:
            raise ConflictError("chat session no longer exists")
        agent_run_id = chat_session.agent_run_id
        editor_session_id = chat_session.editor_session_id
        action = proposal.action
        cell_type = proposal.cell_type
        new_source = proposal.new_source
        target_cell_uuid = proposal.target_cell_uuid
        position_after = proposal.position_after_cell_uuid
        position_at_end = proposal.position_at_end
        proposal.status = "accepted"
        proposal.accepted_at = now
        proposal.accepted_run_id = agent_run_id
        # For ``fix``, inserted_cell_uuid is just the target; the
        # save-path won't re-mint a new UUID for an in-place source
        # change.  For ``propose``, we leave inserted_cell_uuid NULL
        # until the next save tells us the reconciler's pick.
        if action == "fix":
            proposal.inserted_cell_uuid = target_cell_uuid
        session.commit()

    publish(
        editor_session_id,
        ChatEvent(
            kind="cell_proposal_accepted",
            payload={"proposal_id": proposal_id, "action": action},
        ),
    )
    return {
        "proposal_id": proposal_id,
        "action": action,
        "cell_type": cell_type,
        "new_source": new_source,
        "target_cell_uuid": target_cell_uuid,
        "position_after_cell_uuid": position_after,
        "position_at_end": position_at_end,
        "agent_run_id": agent_run_id,
    }


@router.post("/api/notebook/chat/proposals/{proposal_id}/discard")
async def api_discard_proposal(
    request: Request, proposal_id: str
) -> dict[str, Any]:
    """Mark *proposal_id* discarded; fan-out a WS notification.

    Args:
        request: Incoming request.
        proposal_id: The UUID of the proposal to dismiss.

    Returns:
        ``{"proposal_id": str, "status": "discarded"}``.

    Raises:
        ResourceNotFoundError: When the proposal is unknown.
        ConflictError: When already in a terminal state
            (accepted/discarded/expired — except for explain
            proposals which start as ``accepted`` and may be
            discarded to retract).
    """  # noqa: DOC502
    require_user(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)

    with factory() as session:
        proposal = (
            session.query(NotebookCellProposal)
            .filter(NotebookCellProposal.proposal_id == proposal_id)
            .one_or_none()
        )
        if proposal is None:
            raise ResourceNotFoundError.not_found(what=f"proposal {proposal_id!r}")
        # explain proposals start as 'accepted' but can still be
        # discarded (to retract a stale note); propose/fix must be
        # pending.
        if proposal.action != "explain" and proposal.status != "pending":
            raise ConflictError(f"proposal already {proposal.status}")
        if proposal.action == "explain" and proposal.status == "discarded":
            raise ConflictError("proposal already discarded")
        chat_session = session.get(EditorChatSession, proposal.chat_session_id)
        editor_session_id = (
            chat_session.editor_session_id if chat_session else None
        )
        proposal.status = "discarded"
        proposal.accepted_at = now
        session.commit()

    if editor_session_id is not None:
        publish(
            editor_session_id,
            ChatEvent(
                kind="cell_proposal_discarded",
                payload={"proposal_id": proposal_id},
            ),
        )

    return {"proposal_id": proposal_id, "status": "discarded"}


@router.get("/api/notebook/chat/cell/{cell_uuid}/explanations")
async def api_cell_explanations(
    request: Request, cell_uuid: str
) -> dict[str, Any]:
    """Return the accepted explain proposals attached to *cell_uuid*.

    Surfaced by the per-cell social drawer's Explanations tab.
    Discarded explanations are filtered out so the user only sees
    notes the assistant currently stands behind.

    Args:
        request: Incoming request.
        cell_uuid: Stable cell identity UUID.

    Returns:
        ``{"cell_uuid": str, "explanations":
        [{"proposal_id", "explanation", "rationale",
        "agent_run_id", "created_at"}]}`` in chronological order.
    """
    require_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.query(NotebookCellProposal)
            .filter(
                NotebookCellProposal.target_cell_uuid == cell_uuid,
                NotebookCellProposal.action == "explain",
                NotebookCellProposal.status == "accepted",
            )
            .order_by(NotebookCellProposal.created_at.asc())
            .all()
        )
        explanations = [
            {
                "proposal_id": row.proposal_id,
                "explanation": row.explanation,
                "rationale": row.rationale,
                "agent_run_id": row.accepted_run_id,
                "created_at": row.created_at.isoformat()
                if row.created_at
                else None,
            }
            for row in rows
        ]
    return {"cell_uuid": cell_uuid, "explanations": explanations}


__all__ = ["router"]
