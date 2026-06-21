"""Inbound Genie chat webhook for Teams / M365 Copilot connectors.

A registered bot connector points Microsoft Teams (or an M365 Copilot
Studio connector) at ``POST /api/genie/teams/{public_id}/messages``.
Each inbound Bot Framework Activity is authenticated against the
connector's shared-secret token, audited, and — for a user message —
answered through the ordinary grant-enforced Genie path (the exact
``build_context`` → ``generate_sql`` → ``resolve_select_context`` →
``PQL.sql`` recipe the in-app ask surface uses).  The answer is returned
as a reply Activity the channel renders back into the thread.

The connector authenticates as its own principal (``created_by``), so UC
grant enforcement scopes the bot's reach exactly like a human's.  When no
LLM is configured, or the connector is unbound, the bot replies with a
helpful message instead of erroring — a chat surface should always say
something back.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import get_uc_client
from pointlessql.config import get_settings
from pointlessql.exceptions import AuthenticationError, PointlessSQLError, ValidationError
from pointlessql.models import GenieBotConnector
from pointlessql.services import audit as audit_service
from pointlessql.services import genie as genie_service
from pointlessql.services import genie_connectors, genie_teams
from pointlessql.services._executor import run_sync
from pointlessql.services.genie import GenieLLMNotConfiguredError, build_context, generate_sql
from pointlessql.services.notebook._sql_cell import resolve_select_context

router = APIRouter(tags=["genie-teams"])

_MAX_ROWS = 100
_PREVIEW_ROWS = 10


def _bearer(request: Request) -> str:
    """Extract the bearer token from the Authorization header."""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header.strip()


def _run_sql(sql: str, approved: dict[str, str], policies: dict[str, Any] | None) -> Any:
    """Execute a grant-approved SELECT in the sync PQL bridge."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=_MAX_ROWS, table_policies=policies)


def _format_result(sql: str, result: Any) -> str:
    """Render an executed result into a compact chat-friendly answer."""
    lines = [f"```sql\n{sql}\n```"]
    rows = list(result.rows)
    if not rows:
        lines.append("No rows.")
        return "\n".join(lines)
    lines.append(" | ".join(str(col) for col in result.columns))
    for row in rows[:_PREVIEW_ROWS]:
        lines.append(" | ".join("" if value is None else str(value) for value in row))
    if len(rows) > _PREVIEW_ROWS:
        lines.append(f"… and {len(rows) - _PREVIEW_ROWS} more row(s).")
    return "\n".join(lines)


async def _answer(request: Request, connector: GenieBotConnector, question: str) -> str:
    """Answer a question through the grant-enforced Genie path.

    Args:
        request: Incoming FastAPI request (for the UC client).
        connector: The authenticated bot connector.
        question: The mention-stripped user question.

    Returns:
        The answer text — a degraded but helpful message when the
        connector is unbound or no LLM is configured.
    """
    cleaned = question.strip()
    if not cleaned:
        return "Ask me a question about your data and I'll write the SQL."
    slug = connector.genie_space_slug
    if not slug:
        return (
            "This Genie bot isn't bound to a space yet. An admin can bind a "
            "Genie space in the PointlesSQL admin console so I know which "
            "tables I may answer over."
        )
    factory = request.app.state.session_factory
    space = genie_service.get_space(factory, workspace_id=connector.workspace_id, slug=slug)
    if space is None:
        return f"My bound Genie space '{slug}' no longer exists. Ask an admin to re-bind me."
    try:
        context = await build_context(get_uc_client(request), factory, space)
        sql = await generate_sql(
            cleaned,
            context,
            [],
            factory=factory,
            workspace_id=connector.workspace_id,
            settings=get_settings(),
        )
    except GenieLLMNotConfiguredError:
        return (
            "Genie has no language model configured for this workspace yet. "
            "An admin can add a provider key in the admin console."
        )
    except ValidationError as exc:
        return f"I couldn't turn that into SQL: {exc}"
    actor = connector.created_by or f"bot:{connector.name}"
    approved, policies = await resolve_select_context(
        sql,
        uc_client=request.app.state.uc_client,
        actor_email=actor,
        is_admin=False,
    )
    try:
        result = await run_sync(_run_sql, sql, approved, policies)
    except PointlessSQLError as exc:
        return f"The query failed: {exc}"
    return _format_result(sql, result)


@router.post("/api/genie/teams/{public_id}/messages")
async def genie_teams_messages(public_id: str, request: Request) -> dict[str, Any]:
    """Receive a Bot Framework Activity, answer it, and reply.

    Args:
        public_id: The connector's public id from the messaging URL.
        request: Incoming FastAPI request (carries the Activity body and
            the bearer token).

    Returns:
        A Bot Framework reply Activity; a non-message activity is
        acknowledged without an answer.

    Raises:
        AuthenticationError: When the connector is unknown/disabled or the
            presented token does not match.
    """
    factory = request.app.state.session_factory
    connector = genie_connectors.authenticate(
        factory, public_id=public_id, presented_token=_bearer(request)
    )
    if connector is None:
        raise AuthenticationError("invalid Genie connector token")

    try:
        decoded: Any = await request.json()
    except json.JSONDecodeError:
        decoded = {}
    activity = cast("dict[str, Any]", decoded if isinstance(decoded, dict) else {})

    if not genie_teams.is_message(activity):
        return {"type": "message", "text": "", "ignored": True}

    question = genie_teams.extract_question(activity)
    answer = await _answer(request, connector, question)
    await run_sync(
        audit_service.log_action,
        factory,
        0,
        f"bot:{connector.name}",
        "genie.teams.asked",
        f"genie_connector:{connector.public_id}",
        {
            "platform": connector.platform,
            "space": connector.genie_space_slug,
            "question_chars": len(question),
        },
        actor_role="system",
        workspace_id=int(connector.workspace_id),
    )
    return genie_teams.build_reply_activity(activity, answer)
