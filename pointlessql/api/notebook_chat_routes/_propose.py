"""``POST /api/notebook/chat/{id}/{propose,fix,explain}-cell``.

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
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from pointlessql.api._audit_helpers import effective_agent_run_id
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import PermissionDeniedError, ResourceNotFoundError
from pointlessql.models import (
    EditorChatSession,
    NotebookCellProposal,
    NotebookCellProvenance,
)
from pointlessql.services.editor_chat import publish_cell_proposal_created

logger = logging.getLogger(__name__)

router = APIRouter()

_FIX_IDEMPOTENCY_WINDOW_SECONDS: int = 60


# ---------------------------------------------------------------------
# typed proposal bodies.
#
# Pydantic models tighten the field-name surface so a typo on the
# agent side (``rationael`` for ``rationale``) lands as a 422 instead
# of silently dropping the field through ``dict.get(...)``.  The
# field set is mostly required strings + the same ``rationale``
# optional everywhere; we use a small mixin to keep the validators
# co-located with their fields.
# ---------------------------------------------------------------------


def _strip_or_none(value: str | None) -> str | None:
    """Treat empty / whitespace-only strings as missing for optional fields."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ProposeCellBody(BaseModel):
    """Body for ``POST /api/notebook/chat/{id}/propose-cell``."""

    cell_type: Literal["code", "markdown"]
    source: str = Field(..., min_length=1)
    position_after_cell_uuid: str | None = None
    position_at_end: bool = False
    rationale: str | None = None

    @field_validator("source")
    @classmethod
    def _source_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source is required")
        return value

    @field_validator("position_after_cell_uuid", "rationale")
    @classmethod
    def _strip_optionals(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class FixCellBody(BaseModel):
    """Body for ``POST /api/notebook/chat/{id}/fix-cell``."""

    target_cell_uuid: str = Field(..., min_length=1)
    new_source: str = Field(..., min_length=1)
    rationale: str | None = None

    @field_validator("new_source")
    @classmethod
    def _new_source_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("new_source is required")
        return value

    @field_validator("rationale")
    @classmethod
    def _strip_rationale(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class ExplainCellBody(BaseModel):
    """Body for ``POST /api/notebook/chat/{id}/explain-cell``."""

    target_cell_uuid: str = Field(..., min_length=1)
    explanation: str = Field(..., min_length=1)
    rationale: str | None = None

    @field_validator("explanation")
    @classmethod
    def _explanation_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("explanation is required")
        return value

    @field_validator("rationale")
    @classmethod
    def _strip_rationale(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


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
            # transient WS-state mismatch.
            raise ResourceNotFoundError("notebook chat session not found.")
        if agent_run_id is None or chat_session.agent_run_id != agent_run_id:
            # 403 mirrors the Phase-91 SQL chat propose
            # route — agents may only push proposals into the session
            # the caller must drive an agent_run they own.
            raise PermissionDeniedError("X-Agent-Run-Id mismatch for this chat session.")
        # Detach by reading the few fields we need then closing.
        session.expunge(chat_session)
    return chat_session, agent_run_id, workspace_id


@router.post("/api/notebook/chat/{editor_session_id}/propose-cell")
async def api_propose_cell(
    request: Request,
    editor_session_id: str,
    body: ProposeCellBody,
) -> dict[str, Any]:
    """Draft a new cell to insert into the open notebook.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target notebook chat session.
        body: Validated :class:`ProposeCellBody`.

    Returns:
        ``{"proposal_id": str, "action": "propose"}``.

    Raises:
        HTTPException: 403 on X-Agent-Run-Id mismatch; 404 on
            unknown session.  Body validation errors surface as 422
            via FastAPI.
    """  # noqa: DOC502 — HTTPException is what we raise
    chat_session, agent_run_id, workspace_id = _resolve_session(request, editor_session_id)

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
                cell_type=body.cell_type,
                target_cell_uuid=None,
                new_source=body.source,
                explanation=None,
                position_after_cell_uuid=body.position_after_cell_uuid,
                position_at_end=body.position_at_end,
                rationale=body.rationale,
                status="pending",
                created_at=now,
            )
        )
        session.commit()

    publish_cell_proposal_created(
        editor_session_id,
        proposal_id=proposal_id,
        action="propose",
        cell_type=body.cell_type,
        target_cell_uuid=None,
        new_source=body.source,
        explanation=None,
        position_after_cell_uuid=body.position_after_cell_uuid,
        position_at_end=body.position_at_end,
        rationale=body.rationale,
        auto_accepted=False,
        agent_run_id=agent_run_id,
    )
    return {"proposal_id": proposal_id, "action": "propose"}


@router.post("/api/notebook/chat/{editor_session_id}/fix-cell")
async def api_fix_cell(
    request: Request,
    editor_session_id: str,
    body: FixCellBody,
) -> dict[str, Any]:
    """Draft a source replacement for an existing notebook cell.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target chat session.
        body: Validated :class:`FixCellBody`.

    Returns:
        ``{"proposal_id": str, "action": "fix",
        "idempotent_match": bool}``.  ``idempotent_match=True`` when
        an identical pending fix existed in the last 60 seconds and
        its ``proposal_id`` is returned instead of writing a new row.

    Raises:
        HTTPException: 403 on X-Agent-Run-Id mismatch; 404 on
            unknown session.  Body validation errors surface as 422
            via FastAPI.
    """  # noqa: DOC502 — HTTPException bubbles up from _resolve_session
    chat_session, agent_run_id, workspace_id = _resolve_session(request, editor_session_id)

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = _find_idempotent_fix(
            session,
            chat_session.id,
            target_cell_uuid=body.target_cell_uuid,
            new_source=body.new_source,
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
                target_cell_uuid=body.target_cell_uuid,
                new_source=body.new_source,
                explanation=None,
                position_after_cell_uuid=None,
                position_at_end=False,
                rationale=body.rationale,
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
        target_cell_uuid=body.target_cell_uuid,
        new_source=body.new_source,
        explanation=None,
        position_after_cell_uuid=None,
        position_at_end=False,
        rationale=body.rationale,
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
    body: ExplainCellBody,
) -> dict[str, Any]:
    """Attach an explanation to an existing notebook cell (auto-accept).

    Auto-accepts on create — no Run button — and writes a
    ``NotebookCellProvenance`` row immediately so the explanation
    is anchored to the cell without waiting for a save.  This is
    the behavior the user picked during planning: explanations are
    notes, not mutations; persisting them now means they survive
    conversation resets and the revision-history UI can render
    them per cell.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target chat session.
        body: Validated :class:`ExplainCellBody`.

    Returns:
        ``{"proposal_id": str, "action": "explain",
        "status": "accepted"}``.

    Raises:
        HTTPException: 403 on X-Agent-Run-Id mismatch; 404 on
            unknown session.  Body validation errors surface as 422
            via FastAPI.
    """  # noqa: DOC502 — HTTPException bubbles up from _resolve_session
    chat_session, agent_run_id, workspace_id = _resolve_session(request, editor_session_id)

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
                target_cell_uuid=body.target_cell_uuid,
                new_source=None,
                explanation=body.explanation,
                position_after_cell_uuid=None,
                position_at_end=False,
                rationale=body.rationale,
                status="accepted",
                created_at=now,
                accepted_at=now,
                accepted_run_id=agent_run_id,
                inserted_cell_uuid=body.target_cell_uuid,
            )
        )
        session.add(
            NotebookCellProvenance(
                cell_uuid=body.target_cell_uuid,
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
        target_cell_uuid=body.target_cell_uuid,
        new_source=None,
        explanation=body.explanation,
        position_after_cell_uuid=None,
        position_at_end=False,
        rationale=body.rationale,
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
