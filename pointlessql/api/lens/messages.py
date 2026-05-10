"""Lens message endpoint — POST a user turn, get back the assistant turn.

Sprint 65.5 ships non-streaming responses.  The browser chat-UI
shows a "thinking …" skeleton while the round-trip completes; an SSE
streaming variant is queued for when the chat-UI proves out (Sprint
65.7 walkthrough will validate the flow).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_analyst,
)
from pointlessql.services.lens._chat_loop import run_chat_turn

logger = logging.getLogger(__name__)

router = APIRouter()


class PostMessageBody(BaseModel):
    """Input for ``POST /api/lens/sessions/{id}/messages``."""

    content: str = Field(min_length=1, max_length=4000)


class TurnSummary(BaseModel):
    """Output: assistant text + observed tool-calls + token usage."""

    assistant: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


@router.post(
    "/sessions/{session_id}/messages",
    response_model=TurnSummary,
    dependencies=[Depends(require_analyst)],
)
async def post_message_endpoint(
    request: Request,
    session_id: int,
    body: PostMessageBody,
) -> TurnSummary:
    """Append a user message and run one chat-loop iteration.

    Args:
        request: FastAPI request (for app.state).
        session_id: Owning Lens session.
        body: User message payload.

    Returns:
        :class:`TurnSummary` with the assistant reply, tool calls,
        and token / cost stats.
    """
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    out = await run_chat_turn(
        factory=factory,
        settings=settings,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        user_text=body.content,
    )
    return TurnSummary(
        assistant=out["assistant"],
        tool_calls=out["tool_calls"],
        tokens_in=int(out["tokens_in"]),
        tokens_out=int(out["tokens_out"]),
        cost=float(out["cost"]),
    )


class MessageRow(BaseModel):
    """One row in the persisted transcript."""

    id: int
    role: str
    content: str | None
    tool_name: str | None
    tool_status: str | None
    cost_estimate: float
    created_at: str


class MessageList(BaseModel):
    """``GET /api/lens/sessions/{id}/messages`` response shape."""

    messages: list[MessageRow]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageList,
    dependencies=[Depends(require_analyst)],
)
def list_messages_endpoint(
    request: Request,
    session_id: int,
) -> MessageList:
    """Return the persisted transcript for *session_id*.

    Args:
        request: FastAPI request.
        session_id: Owning Lens session.

    Returns:
        :class:`MessageList` ordered chronologically.
    """
    from pointlessql.services.lens import get_session, list_session_messages

    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    # Auth-check + workspace-isolation via get_session.
    get_session(
        factory,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
    )
    msgs = list_session_messages(factory, session_id=session_id)
    return MessageList(
        messages=[
            MessageRow(
                id=int(m.id),
                role=str(m.role),
                content=m.content,
                tool_name=m.tool_name,
                tool_status=m.tool_status,
                cost_estimate=float(m.cost_estimate or 0.0),
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in msgs
        ]
    )
