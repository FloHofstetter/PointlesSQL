"""``POST /api/sql/chat/{session_id}/propose`` — chat DML/DDL draft.

Called by the ``pql_propose_sql`` plugin tool when the LLM wants
to issue a non-SELECT.  We never execute the SQL here: the route
parses + classifies it (rejecting SELECT/EXPLAIN with 400), writes
a :class:`ChatProposal` row, and fans out a ``proposal_created``
event on the chat broker so the WS coroutine for the session
forwards the draft to the editor as a "Run / Discard" banner.

Idempotency: if a proposal with identical SQL + kind was created
in the same session within 60 seconds, the existing
``proposal_id`` is returned instead of writing a new row.
Prevents WS-notify spam from agent retries.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from pointlessql.api._audit_helpers import effective_agent_run_id
from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from pointlessql.models import ChatProposal, EditorChatSession
from pointlessql.pql.sql_parser import StmtType, parse_and_classify
from pointlessql.services.editor_chat import publish_proposal_created

logger = logging.getLogger(__name__)

router = APIRouter()


class ProposeSqlBody(BaseModel):
    """Body for ``POST /api/sql/chat/{id}/propose``.

    The plugin tool historically posted ``sql`` while some older
    callers used ``sql_text``; both names round-trip identically
    via a populate-by-name alias so we do not break the existing
    contract while moving off ``dict[str, Any]``.
    """

    sql: str = Field(default="", alias="sql")
    sql_text: str | None = None
    rationale: str | None = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _coalesce_sql(self) -> ProposeSqlBody:
        # ``sql_text`` is the legacy alias; merge into ``sql`` so the
        # route reads a single field.  Pydantic v2 forbids mutating
        # the model after validation by default — we rebuild via
        # ``model_copy`` to stay within the supported surface.
        chosen = (self.sql or self.sql_text or "").strip()
        if not chosen:
            raise ValueError("sql is required")
        object.__setattr__(self, "sql", chosen)
        object.__setattr__(self, "sql_text", None)
        return self

    @field_validator("rationale")
    @classmethod
    def _strip_rationale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


_IDEMPOTENCY_WINDOW_SECONDS: int = 60

_DDL_TYPES: frozenset[StmtType] = frozenset(
    {
        StmtType.DROP_TABLE,
        StmtType.CREATE_SCHEMA,
        StmtType.DROP_SCHEMA,
        StmtType.ALTER_TABLE,
    }
)
_DML_TYPES: frozenset[StmtType] = frozenset(
    {
        StmtType.INSERT_FROM_SELECT,
        StmtType.UPDATE,
        StmtType.DELETE,
        StmtType.MERGE,
        StmtType.CREATE_TABLE_AS,
    }
)


@router.post("/api/sql/chat/{editor_session_id}/propose")
async def api_propose_sql(
    request: Request,
    editor_session_id: str,
    body: ProposeSqlBody,
) -> dict[str, Any]:
    """Draft a non-SELECT SQL statement for the human's review.

    ``kind`` is derived server-side from the parsed statement type
    so agents can't lie about it.  Invalid SQL and SELECT
    statements propagate :class:`ValidationError` (400) from
    :func:`_classify_proposal_kind`.

    Args:
        request: Incoming request — must carry an
            ``X-Agent-Run-Id`` matching the session's agent run.
        editor_session_id: UUID7 of the target chat session.
        body: Validated :class:`ProposeSqlBody`.

    Returns:
        ``{"proposal_id": str, "kind": "dml" | "ddl",
        "idempotent_match": bool}``.  ``idempotent_match=True``
        when a duplicate proposal was returned instead of created.

    Raises:
        PermissionDeniedError: On ``X-Agent-Run-Id`` mismatch.
        ResourceNotFoundError: When the session is unknown.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)

    sql_text = body.sql
    rationale = body.rationale

    kind = _classify_proposal_kind(sql_text)
    factory = request.app.state.session_factory
    agent_run_id = effective_agent_run_id(request)

    with factory() as session:
        chat_session = (
            session.query(EditorChatSession)
            .filter(EditorChatSession.editor_session_id == editor_session_id)
            .one_or_none()
        )
        if chat_session is None:
            raise ResourceNotFoundError("chat session not found")
        if agent_run_id is None or chat_session.agent_run_id != agent_run_id:
            raise PermissionDeniedError(
                "X-Agent-Run-Id mismatch for this chat session",
            )

        existing = _find_idempotent_match(session, chat_session.id, sql_text, kind)
        if existing is not None:
            return {
                "proposal_id": existing.proposal_id,
                "kind": existing.kind,
                "idempotent_match": True,
            }

        proposal_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.UTC)
        session.add(
            ChatProposal(
                proposal_id=proposal_id,
                chat_session_id=chat_session.id,
                workspace_id=workspace_id,
                sql_text=sql_text,
                kind=kind,
                rationale=rationale,
                status="pending",
                created_at=now,
            )
        )
        session.commit()

    publish_proposal_created(
        editor_session_id=editor_session_id,
        proposal_id=proposal_id,
        sql_text=sql_text,
        kind=kind,
        rationale=rationale,
    )
    return {
        "proposal_id": proposal_id,
        "kind": kind,
        "idempotent_match": False,
    }


def _classify_proposal_kind(sql_text: str) -> str:
    """Return ``"dml"`` / ``"ddl"`` or raise 400 for SELECT/unsupported."""
    try:
        _, stype = parse_and_classify(sql_text)
    except ValidationError as exc:
        raise ValidationError(f"sql parse failed: {exc}") from exc
    if stype is StmtType.SELECT:
        raise ValidationError(
            "SELECT must use pql_query, not pql_propose_sql — "
            "the chat tool routes reads through the dispatcher "
            "directly so the human sees rows immediately.",
        )
    if stype in _DML_TYPES:
        return "dml"
    if stype in _DDL_TYPES:
        return "ddl"
    raise ValidationError(
        f"unsupported statement type: {stype.value}",
    )


def _find_idempotent_match(
    session: Any,
    chat_session_id: int,
    sql_text: str,
    kind: str,
) -> ChatProposal | None:
    """Return a within-window identical pending proposal, if any."""
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(
        seconds=_IDEMPOTENCY_WINDOW_SECONDS
    )
    return (
        session.query(ChatProposal)
        .filter(
            ChatProposal.chat_session_id == chat_session_id,
            ChatProposal.sql_text == sql_text,
            ChatProposal.kind == kind,
            ChatProposal.status == "pending",
            ChatProposal.created_at >= cutoff,
        )
        .order_by(ChatProposal.created_at.desc())
        .first()
    )


__all__ = ["router"]
