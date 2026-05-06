"""Per-run LLM tool-call recording endpoint.

The Hermes plugin's ``post_tool_call`` hook posts to
``/api/agent-runs/{run_id}/tool-call`` for any tool whose name
starts with ``pql_``.  Persists the row and emits a
``pointlessql.agent_run.tool_call`` CloudEvent so external
subscribers can rebuild the agent's reasoning trace from the event
stream.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models import AgentRunToolCall
from pointlessql.models.agent_runs import AgentRun
from pointlessql.services.agent_runs import EVENT_TYPE_TOOL_CALL, emit_agent_run_event

router = APIRouter()


@router.post("/api/agent-runs/{run_id}/tool-call")
async def api_record_tool_call(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Record one LLM tool invocation against an agent run.

    The Hermes plugin's ``post_tool_call`` hook posts here for any
    tool whose name starts with ``pql_``.  Persists the row in
    ``agent_run_tool_calls`` and emits a
    ``pointlessql.agent_run.tool_call`` CloudEvent so external
    subscribers can rebuild the agent's reasoning trace from the
    event stream.

    The endpoint is intentionally lenient on missing optional
    fields — the plugin should never have to know the schema; if
    ``args_json`` is empty we store ``"{}"``, if ``called_at`` is
    missing we use the request wall-clock.

    Args:
        request: Incoming FastAPI request.
        run_id: UUID of the owning agent run.
        body: JSON ``{tool_name, args_json?, result_summary?,
            duration_ms?, called_at?}``.

    Returns:
        ``{"id": <new_row_id>, "tool_name": ..., "called_at": ...}``.

    Raises:
        ValidationError: Missing/empty ``tool_name``.
        CatalogNotFoundError: No run with that id.
    """
    tool_name_raw = body.get("tool_name")
    if not isinstance(tool_name_raw, str) or not tool_name_raw.strip():
        raise ValidationError("tool_name must be a non-empty string")
    tool_name = tool_name_raw.strip()[:64]

    args_json_raw = body.get("args_json")
    if isinstance(args_json_raw, str) and args_json_raw.strip():
        args_json = args_json_raw
    elif isinstance(args_json_raw, dict):
        args_json = json.dumps(args_json_raw, sort_keys=True, default=str)
    else:
        args_json = "{}"

    summary_raw = body.get("result_summary")
    result_summary: str | None = None
    if isinstance(summary_raw, str) and summary_raw:
        result_summary = summary_raw[:2000]

    duration_raw = body.get("duration_ms")
    duration_ms: int | None = None
    if isinstance(duration_raw, (int, float)) and duration_raw >= 0:
        duration_ms = int(duration_raw)

    called_at_raw = body.get("called_at")
    if isinstance(called_at_raw, str) and called_at_raw.strip():
        try:
            called_at = datetime.fromisoformat(called_at_raw)
        except ValueError as exc:
            raise ValidationError("called_at must be ISO-8601 when provided") from exc
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=UTC)
    else:
        called_at = datetime.now(UTC)

    factory = request.app.state.session_factory
    with factory() as session:
        run_row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if run_row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        # Denormalise workspace_id from the parent.
        tool_row = AgentRunToolCall(
            workspace_id=int(run_row.workspace_id),
            agent_run_id=run_id,
            tool_name=tool_name,
            args_json=args_json,
            result_summary=result_summary,
            duration_ms=duration_ms,
            called_at=called_at,
        )
        session.add(tool_row)
        session.commit()
        session.refresh(tool_row)
        new_id = tool_row.id
        session.expunge(tool_row)

    # ``id`` keys the CloudEvent's source URL to the parent run id
    # so emit_agent_run_event() persists the envelope under the
    # correct ``agent_run_events.agent_run_id`` FK.  The
    # tool-call row's primary key surfaces as ``tool_call_id``.
    payload = {
        "id": run_id,
        "tool_call_id": new_id,
        "tool_name": tool_name,
        "called_at": called_at.isoformat(),
        "duration_ms": duration_ms,
    }
    await audit(
        request,
        "record_agent_run_tool_call",
        f"agent_run:{run_id}",
        {"tool_name": tool_name},
    )
    await emit_agent_run_event(EVENT_TYPE_TOOL_CALL, payload, session_factory=factory)
    return payload
