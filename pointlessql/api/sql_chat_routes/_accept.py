"""``POST /api/sql/chat/proposals/{proposal_id}/accept`` and ``/discard``.

Lifecycle endpoints for :class:`ChatProposal` rows.  ``/accept``
marks the row ``status="accepted"`` (or ``"expired"`` when older
than 24h) and returns the SQL + the chat session's
``agent_run_id`` so the editor's regular ``POST /api/sql/execute``
call lands its operation row against the chat run.  ``/discard``
just sets ``status="discarded"`` for audit; the WS notify is
fan-outed so other open tabs / observers see the dismissal.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.dependencies import require_user
from pointlessql.models import ChatProposal, EditorChatSession
from pointlessql.services.sql_chat import ChatEvent, publish

logger = logging.getLogger(__name__)

router = APIRouter()

_PROPOSAL_TTL_HOURS: int = 24


@router.post("/api/sql/chat/proposals/{proposal_id}/accept")
async def api_accept_proposal(
    request: Request, proposal_id: str
) -> dict[str, Any]:
    """Mark *proposal_id* accepted; return SQL + agent_run_id.

    The actual ``/api/sql/execute`` call still comes from the
    editor's normal Run button — but the ``agent_run_id`` we
    return is the chat session's, so the operation row hangs off
    the same run as every chat tool-call.

    Args:
        request: Incoming request.  Must be authenticated.
        proposal_id: The UUID returned by the propose tool.

    Returns:
        ``{"sql": str, "agent_run_id": str, "kind": "dml"|"ddl"}``.

    Raises:
        HTTPException: 404 when the proposal is unknown; 409 when
            already accepted/discarded or older than 24h.
    """  # noqa: DOC502 — HTTPException raised explicitly
    require_user(request)
    factory = request.app.state.session_factory

    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(hours=_PROPOSAL_TTL_HOURS)

    with factory() as session:
        proposal = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one_or_none()
        )
        if proposal is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        if proposal.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"proposal already {proposal.status}",
            )
        # SQLite returns naive datetimes; coerce so the comparison
        # against a tz-aware ``cutoff`` does not raise.
        created_at = proposal.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.UTC)
        if created_at < cutoff:
            proposal.status = "expired"
            proposal.accepted_at = now
            session.commit()
            raise HTTPException(
                status_code=409,
                detail=(
                    "proposal is older than 24 hours and cannot be "
                    "accepted; ask the chat to redraft."
                ),
            )
        chat_session = session.get(EditorChatSession, proposal.chat_session_id)
        if chat_session is None:
            raise HTTPException(
                status_code=409,
                detail="chat session no longer exists",
            )
        agent_run_id = chat_session.agent_run_id
        editor_session_id = chat_session.editor_session_id
        proposal.status = "accepted"
        proposal.accepted_at = now
        proposal.accepted_run_id = agent_run_id
        session.commit()
        sql_text = proposal.sql_text
        kind = proposal.kind

    publish(
        editor_session_id,
        ChatEvent(
            kind="proposal_accepted",
            payload={"proposal_id": proposal_id},
        ),
    )

    return {
        "proposal_id": proposal_id,
        "sql": sql_text,
        "kind": kind,
        "agent_run_id": agent_run_id,
    }


@router.post("/api/sql/chat/proposals/{proposal_id}/discard")
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
        HTTPException: 404 when the proposal is unknown; 409 when
            already accepted/discarded/expired.
    """  # noqa: DOC502 — HTTPException raised explicitly
    require_user(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)

    with factory() as session:
        proposal = (
            session.query(ChatProposal)
            .filter(ChatProposal.proposal_id == proposal_id)
            .one_or_none()
        )
        if proposal is None:
            raise HTTPException(status_code=404, detail="proposal not found")
        if proposal.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"proposal already {proposal.status}",
            )
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
                kind="proposal_discarded",
                payload={"proposal_id": proposal_id},
            ),
        )

    return {"proposal_id": proposal_id, "status": "discarded"}


__all__ = ["router"]
