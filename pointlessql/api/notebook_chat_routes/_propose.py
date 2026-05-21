"""``POST /api/notebook/chat/{id}/{propose,fix,explain}-cell`` (Phase 96).

Three sibling routes that the in-process AI assistant calls via
the new ``pql_propose_cell`` / ``pql_fix_cell`` / ``pql_explain_cell``
plugin tools.  Each writes a :class:`NotebookCellProposal` row
(polymorphic — discriminated by ``action``), fans out a
``cell_proposal_created`` broker frame, and returns the proposal
id + (for the ``fix`` route) the ``idempotent_match`` flag.

Idempotency: a 60 s window on identical fix-against-same-cell
prevents agent retry loops from spamming the editor with duplicate
banners.  Propose has no idempotency (every "add a cell" request is
its own draft).  Explain has no idempotency (every accepted
explanation persists; the user can attach many to the same cell).

Explain proposals are written with ``status='accepted'`` directly
because there is no Run button — they are notes, not mutations.
Provenance is written inline at create-time for explain; for
propose + fix it is deferred to the next ``/api/notebooks/save``
when the reconciler has the final ``cell_uuid``.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from pointlessql.api._audit_helpers import effective_agent_run_id
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.models import (
    EditorChatSession,
    NotebookCellProposal,
    NotebookCellProvenance,
)
from pointlessql.services.editor_chat import publish_cell_proposal_created

logger = logging.getLogger(__name__)

router = APIRouter()

_FIX_IDEMPOTENCY_WINDOW_SECONDS: int = 60


def _resolve_session(
    request: Request, editor_session_id: str
) -> tuple[EditorChatSession, str, int]:
    """Look up the chat session + verify the X-Agent-Run-Id header."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    agent_run_id = effective_agent_run_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        chat_session = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .one_or_none()
        )
        if chat_session is None:
            # bare-http-ok: 404 for missing chat session — no domain
            # exception class for this transient WS-state mismatch.
            raise HTTPException(
                status_code=404, detail="notebook chat session not found"
            )
        if agent_run_id is None or chat_session.agent_run_id != agent_run_id:
            # bare-http-ok: 403 mirrors the Phase-91 SQL chat propose
            # route — agents may only push proposals into the session
            # whose agent_run they own; no domain auth class fits.
            raise HTTPException(
                status_code=403,
                detail="X-Agent-Run-Id mismatch for this chat session",
            )
        # Detach by reading the few fields we need then closing.
        session.expunge(chat_session)
    return chat_session, agent_run_id, workspace_id


@router.post("/api/notebook/chat/{editor_session_id}/propose-cell")
async def api_propose_cell(
    request: Request,
    editor_session_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Draft a new cell to insert into the open notebook.

    Body shape:
        ``{"cell_type": "code"|"markdown", "source": str,
        "position_after_cell_uuid": str | None,
        "position_at_end": bool, "rationale": str | None}``.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target notebook chat session.
        body: JSON payload (see above).

    Returns:
        ``{"proposal_id": str, "action": "propose"}``.

    Raises:
        HTTPException: 400 on invalid body; 403 on
            X-Agent-Run-Id mismatch; 404 on unknown session.
    """  # noqa: DOC502 — HTTPException is what we raise
    cell_type = body.get("cell_type")
    source = body.get("source")
    if cell_type not in {"code", "markdown"}:
        # bare-http-ok: 400 for invalid request body; agent should
        # re-call with a valid cell_type — no domain exception fits.
        raise HTTPException(
            status_code=400,
            detail="cell_type must be 'code' or 'markdown'",
        )
    if not isinstance(source, str) or not source.strip():
        # bare-http-ok: 400 for missing required body field.
        raise HTTPException(
            status_code=400, detail="source is required"
        )
    rationale = body.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        rationale = None
    position_after = body.get("position_after_cell_uuid")
    if position_after is not None and not isinstance(position_after, str):
        position_after = None
    position_at_end = bool(body.get("position_at_end") or False)

    chat_session, agent_run_id, workspace_id = _resolve_session(
        request, editor_session_id
    )

    proposal_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    factory = request.app.state.session_factory
    with factory() as session:
        session.add(
            NotebookCellProposal(
                proposal_id=proposal_id,
                chat_session_id=chat_session.id,
                workspace_id=workspace_id,
                action="propose",
                cell_type=cell_type,
                target_cell_uuid=None,
                new_source=source,
                explanation=None,
                position_after_cell_uuid=position_after,
                position_at_end=position_at_end,
                rationale=rationale,
                status="pending",
                created_at=now,
            )
        )
        session.commit()

    publish_cell_proposal_created(
        editor_session_id,
        proposal_id=proposal_id,
        action="propose",
        cell_type=cell_type,
        target_cell_uuid=None,
        new_source=source,
        explanation=None,
        position_after_cell_uuid=position_after,
        position_at_end=position_at_end,
        rationale=rationale,
        auto_accepted=False,
        agent_run_id=agent_run_id,
    )
    return {"proposal_id": proposal_id, "action": "propose"}


@router.post("/api/notebook/chat/{editor_session_id}/fix-cell")
async def api_fix_cell(
    request: Request,
    editor_session_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Draft a source replacement for an existing notebook cell.

    Body shape:
        ``{"target_cell_uuid": str, "new_source": str,
        "rationale": str | None}``.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target chat session.
        body: JSON payload (see *Body shape* above).

    Returns:
        ``{"proposal_id": str, "action": "fix",
        "idempotent_match": bool}``.  ``idempotent_match=True`` when
        an identical pending fix existed in the last 60 seconds and
        its ``proposal_id`` is returned instead of writing a new row.

    Raises:
        HTTPException: 400 on invalid body; 403 on
            X-Agent-Run-Id mismatch; 404 on unknown session.
    """
    target_cell_uuid = body.get("target_cell_uuid")
    new_source = body.get("new_source")
    if not isinstance(target_cell_uuid, str) or not target_cell_uuid:
        # bare-http-ok: 400 for missing required body field.
        raise HTTPException(
            status_code=400, detail="target_cell_uuid is required"
        )
    if not isinstance(new_source, str) or not new_source.strip():
        # bare-http-ok: 400 for missing required body field.
        raise HTTPException(
            status_code=400, detail="new_source is required"
        )
    rationale = body.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        rationale = None

    chat_session, agent_run_id, workspace_id = _resolve_session(
        request, editor_session_id
    )

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = _find_idempotent_fix(
            session,
            chat_session.id,
            target_cell_uuid=target_cell_uuid,
            new_source=new_source,
        )
        if existing is not None:
            return {
                "proposal_id": existing.proposal_id,
                "action": "fix",
                "idempotent_match": True,
            }
        proposal_id = str(uuid.uuid4())
        session.add(
            NotebookCellProposal(
                proposal_id=proposal_id,
                chat_session_id=chat_session.id,
                workspace_id=workspace_id,
                action="fix",
                cell_type=None,
                target_cell_uuid=target_cell_uuid,
                new_source=new_source,
                explanation=None,
                position_after_cell_uuid=None,
                position_at_end=False,
                rationale=rationale,
                status="pending",
                created_at=now,
            )
        )
        session.commit()

    publish_cell_proposal_created(
        editor_session_id,
        proposal_id=proposal_id,
        action="fix",
        cell_type=None,
        target_cell_uuid=target_cell_uuid,
        new_source=new_source,
        explanation=None,
        position_after_cell_uuid=None,
        position_at_end=False,
        rationale=rationale,
        auto_accepted=False,
        agent_run_id=agent_run_id,
    )
    return {
        "proposal_id": proposal_id,
        "action": "fix",
        "idempotent_match": False,
    }


@router.post("/api/notebook/chat/{editor_session_id}/explain-cell")
async def api_explain_cell(
    request: Request,
    editor_session_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Attach an explanation to an existing notebook cell (auto-accept).

    Body shape:
        ``{"target_cell_uuid": str, "explanation": str,
        "rationale": str | None}``.

    Auto-accepts on create — no Run button — and writes a
    ``NotebookCellProvenance`` row immediately so the explanation
    is anchored to the cell without waiting for a save.  This is
    the behavior the user picked during planning: explanations are
    notes, not mutations; persisting them now means they survive
    conversation resets and Phase 97 revision history can render
    them per cell.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target chat session.
        body: JSON payload (see *Body shape* above).

    Returns:
        ``{"proposal_id": str, "action": "explain",
        "status": "accepted"}``.

    Raises:
        HTTPException: 400 on invalid body; 403 on
            X-Agent-Run-Id mismatch; 404 on unknown session.
    """
    target_cell_uuid = body.get("target_cell_uuid")
    explanation = body.get("explanation")
    if not isinstance(target_cell_uuid, str) or not target_cell_uuid:
        # bare-http-ok: 400 for missing required body field.
        raise HTTPException(
            status_code=400, detail="target_cell_uuid is required"
        )
    if not isinstance(explanation, str) or not explanation.strip():
        # bare-http-ok: 400 for missing required body field.
        raise HTTPException(
            status_code=400, detail="explanation is required"
        )
    rationale = body.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        rationale = None

    chat_session, agent_run_id, workspace_id = _resolve_session(
        request, editor_session_id
    )

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    proposal_id = str(uuid.uuid4())
    with factory() as session:
        session.add(
            NotebookCellProposal(
                proposal_id=proposal_id,
                chat_session_id=chat_session.id,
                workspace_id=workspace_id,
                action="explain",
                cell_type=None,
                target_cell_uuid=target_cell_uuid,
                new_source=None,
                explanation=explanation,
                position_after_cell_uuid=None,
                position_at_end=False,
                rationale=rationale,
                status="accepted",
                created_at=now,
                accepted_at=now,
                accepted_run_id=agent_run_id,
                inserted_cell_uuid=target_cell_uuid,
            )
        )
        session.add(
            NotebookCellProvenance(
                cell_uuid=target_cell_uuid,
                agent_run_id=agent_run_id,
                proposal_id=proposal_id,
                action="explain",
                created_at=now,
            )
        )
        session.commit()

    publish_cell_proposal_created(
        editor_session_id,
        proposal_id=proposal_id,
        action="explain",
        cell_type=None,
        target_cell_uuid=target_cell_uuid,
        new_source=None,
        explanation=explanation,
        position_after_cell_uuid=None,
        position_at_end=False,
        rationale=rationale,
        auto_accepted=True,
        agent_run_id=agent_run_id,
    )
    return {
        "proposal_id": proposal_id,
        "action": "explain",
        "status": "accepted",
    }


def _find_idempotent_fix(
    session: Any,
    chat_session_id: int,
    *,
    target_cell_uuid: str,
    new_source: str,
) -> NotebookCellProposal | None:
    """Return an in-window identical pending fix proposal, if any."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=_FIX_IDEMPOTENCY_WINDOW_SECONDS
    )
    return (
        session.query(NotebookCellProposal)
        .filter(
            NotebookCellProposal.chat_session_id == chat_session_id,
            NotebookCellProposal.action == "fix",
            NotebookCellProposal.target_cell_uuid == target_cell_uuid,
            NotebookCellProposal.new_source == new_source,
            NotebookCellProposal.status == "pending",
            NotebookCellProposal.created_at >= cutoff,
        )
        .order_by(NotebookCellProposal.created_at.desc())
        .first()
    )


__all__ = ["router"]
