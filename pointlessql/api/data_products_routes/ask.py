"""Ask-this-data-product routes — a DP-scoped natural-language panel.

A thin consumer-facing wrapper over the Lens chat engine: it opens a
Lens session pre-seeded with *this* product's tables, columns, and
business concepts so the model answers grounded in the product the user
is looking at, and runs message turns through the same chat-loop (which
executes governed, read-only SELECTs via the ``query`` tool).

Gated by ``require_user`` rather than ``require_analyst`` because the
panel is for non-technical business consumers — the per-table SELECT
gate inside the query executor is what actually protects the data, so a
consumer who lacks access gets a clean "I can't read that" rather than
rows.  The model can always *explain* the product from the seeded
context even without query access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pointlessql.api.data_products_routes._shared import (
    load_one,
    serialise_table_contracts,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.services.data_product_semantic import list_concepts
from pointlessql.services.lens import (
    append_message,
    create_session,
    get_session,
    list_provider_creds,
)
from pointlessql.services.lens._chat_loop import run_chat_turn

router = APIRouter(tags=["data-products"])


class AskSessionInfo(BaseModel):
    """Response for opening a DP-scoped Ask session."""

    session_id: int
    provider: str
    configured: bool
    intro: str


class AskMessageBody(BaseModel):
    """Input for posting a question to a DP-scoped Ask session."""

    content: str = Field(min_length=1, max_length=4000)


class AskTurn(BaseModel):
    """Assistant reply + the rows any query tool-call returned."""

    assistant: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    cost: float = 0.0


def _pick_provider(factory: Any, workspace_id: int, settings: Any) -> tuple[str, str, bool]:
    """Choose a configured provider for the session.

    Prefers an enabled ``anthropic`` credential, else the first enabled
    one, else defaults to ``anthropic`` un-configured (the first message
    then surfaces a clean "provider not configured" error the panel can
    render as a hint).

    Args:
        factory: Session factory used to look up the workspace's stored
            provider credentials.
        workspace_id: Workspace whose provider credentials are consulted.
        settings: Application settings supplying the per-provider default
            model names when the credential does not pin one.

    Returns:
        ``(provider, model, configured)``.
    """
    enabled = [c for c in list_provider_creds(factory, workspace_id=workspace_id) if c.enabled]
    chosen = next((c for c in enabled if c.provider == "anthropic"), None) or (
        enabled[0] if enabled else None
    )
    provider = chosen.provider if chosen else "anthropic"
    default_model = settings.lens.model_default(provider)
    model = chosen.default_model if chosen and chosen.default_model else default_model
    return provider, model, chosen is not None


def _grounding(
    catalog: str,
    schema: str,
    name: str,
    description: str,
    tables: list[dict[str, Any]],
    concepts: list[Any],
    sample_sql: str | None,
) -> str:
    """Build the context message that scopes the model to this product."""
    lines = [
        f'You are helping a business user understand and use the data product "{name}" '
        f"({catalog}.{schema}).",
        f"Description: {description or 'no description provided'}.",
        "",
        "Tables you can query — use these fully-qualified names verbatim in any SQL:",
    ]
    for table in tables:
        cols = ", ".join(f"{c['name']} ({c['type']})" for c in table.get("columns", []))
        lines.append(f"- {catalog}.{schema}.{table['name']}: {cols or 'no columns declared'}")
    if concepts:
        lines.append("")
        lines.append("Business concepts in this product:")
        for concept in concepts:
            desc = getattr(concept, "description", None)
            maps_to = getattr(concept, "maps_to", None)
            suffix = f" — {desc}" if desc else ""
            target = f" (maps to {maps_to})" if maps_to else ""
            lines.append(f"- {getattr(concept, 'concept', '')}{suffix}{target}")
    if sample_sql:
        lines.append("")
        lines.append(f"Example query for this product:\n{sample_sql}")
    lines.extend(
        [
            "",
            "When the user asks for figures or rows, write a read-only SELECT against the "
            "tables above and run it with the `query` tool, then explain the result in "
            "plain, non-technical language.  Keep answers concise and friendly.",
        ]
    )
    return "\n".join(lines)


@router.post("/api/data-products/{catalog}/{schema}/ask/sessions", response_model=AskSessionInfo)
def open_ask_session(catalog: str, schema: str, request: Request) -> AskSessionInfo:
    """Open a Lens session pre-seeded with this product's context.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        :class:`AskSessionInfo` with the new session id, the chosen
        provider, whether a credential is configured, and an intro line
        for the panel to show.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    dp_row, contract, _steward_email, _steward_display = load_one(
        factory, workspace_id, catalog, schema
    )

    provider, model, configured = _pick_provider(factory, workspace_id, settings)
    session = create_session(
        factory,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        title=f"Ask: {catalog}.{schema}",
        llm_provider=provider,
        llm_model=model,
    )

    tables = serialise_table_contracts(contract)
    concepts = list_concepts(factory, data_product_id=int(dp_row.id))
    grounding = _grounding(
        catalog,
        schema,
        contract.name,
        contract.description or "",
        tables,
        concepts,
        dp_row.sample_sql,
    )
    intro = (
        f"Hi! I can help you explore **{contract.name}**.  Ask what this data product "
        "contains, what a column means, or for figures like totals and counts — I'll "
        "query it for you and answer in plain language."
    )
    # Seed user(context) + assistant(ack) so the transcript starts on a
    # user turn (Anthropic requires that) and the model is grounded.
    append_message(factory, session_id=int(session.id), role="user", content=grounding)
    append_message(factory, session_id=int(session.id), role="assistant", content=intro)

    return AskSessionInfo(
        session_id=int(session.id), provider=provider, configured=configured, intro=intro
    )


@router.post(
    "/api/data-products/{catalog}/{schema}/ask/sessions/{session_id}/messages",
    response_model=AskTurn,
)
async def post_ask_message(
    catalog: str, schema: str, session_id: int, request: Request, body: AskMessageBody
) -> AskTurn:
    """Run one question → answer turn on a DP-scoped Ask session.

    Args:
        catalog: UC catalog segment (path scoping only).
        schema: UC schema segment (path scoping only).
        session_id: The Ask session opened by :func:`open_ask_session`.
        request: Incoming FastAPI request.
        body: The user's question.

    Returns:
        :class:`AskTurn` with the assistant text, observed tool calls
        (carrying any query result rows), and the turn cost.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    # Ownership + workspace isolation — raises 404 when the session
    # isn't this user's; keeps one consumer off another's transcript.
    get_session(
        factory,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
    )
    out = await run_chat_turn(
        factory=factory,
        settings=settings,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        user_text=body.content,
    )
    return AskTurn(
        assistant=out["assistant"],
        tool_calls=out["tool_calls"],
        cost=float(out["cost"]),
    )
