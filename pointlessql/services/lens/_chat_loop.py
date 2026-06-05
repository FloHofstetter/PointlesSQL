"""Lens chat loop — one user-message → assistant-message round-trip.

Drives the LLM provider + tool dispatch in a small loop:

1. Append the user message to ``lens_messages``.
2. Reload the session transcript from DB.
3. Build the provider-specific message history.
4. Call the LLM provider (``chat_with_tools``).
5. If the LLM returned tool-calls, dispatch each via
   :func:`execute_tool_with_audit`, append a tool-result message,
   and loop back to step 4.
6. When no more tool-calls land, persist the final assistant text
   and return it.

Hard caps:

* ``max_tool_iterations`` (default 8) — prevents an LLM that keeps
  asking for tool calls from looping forever.
* The session's :class:`LensSettings.max_messages_per_session` cap is
  enforced by :func:`append_message` callers; this module trusts it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import PointlessSQLError, ValidationError
from pointlessql.services.lens._chat_logic import (
    assistant_tool_call_message,
    classify_tool_exception,
    completion_response,
    loop_cap_message,
    observed_tool_call_record,
    should_persist_loop_cap,
    to_provider_history,
    tool_result_message,
)
from pointlessql.services.lens._messages import (
    append_message,
    list_session_messages,
)
from pointlessql.services.lens._provider_creds import decrypt_provider_key
from pointlessql.services.lens._sessions import get_session
from pointlessql.services.lens.llm_provider import get_provider
from pointlessql.services.lens.tools import (
    LensToolError,
    SessionContext,
    execute_tool_with_audit,
)
from pointlessql.types import ErrorCode

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.config import Settings

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 8


class LensProviderNotConfiguredError(ValidationError):
    """Raised when the workspace has no enabled provider credential.

    Attributes:
        error_code: :data:`ErrorCode.LENS_PROVIDER_NOT_CONFIGURED`.
    """

    error_code: ErrorCode = ErrorCode.LENS_PROVIDER_NOT_CONFIGURED


def _principal_uc_client(
    factory: sessionmaker[Session],
    settings: Settings,
    owner_id: int,
) -> Any:
    """Build a principal-scoped UC facade for the analyst, or ``None``.

    The ``query`` tool needs a live UC client to resolve + SELECT-gate
    the tables a generated SELECT touches; the catalog / describe tools
    use it too.  Returns ``None`` when the owner can't be resolved to an
    email, so detached callers keep the no-runtime tool behaviour.
    Mirrors the per-request construction in ``get_uc_client`` — no
    explicit close, the underlying HTTP client is GC-managed exactly as
    on the route path.
    """
    from pointlessql.models import User
    from pointlessql.services.unitycatalog import UnityCatalogClient

    with factory() as session:
        user = session.get(User, owner_id)
        email = user.email if user else None
    if not email:
        return None
    return UnityCatalogClient.for_principal(settings, email)


async def run_chat_turn(
    *,
    factory: sessionmaker[Session],
    settings: Settings,
    session_id: int,
    workspace_id: int,
    owner_id: int,
    user_text: str,
) -> dict[str, Any]:
    """Drive one user → assistant round-trip on a Lens session.

    Persists the user message, reloads the transcript, runs the
    provider/tool loop, and returns the assistant message + a flat
    list of tool calls observed.

    Args:
        factory: SQLAlchemy session factory.
        settings: Resolved :class:`Settings`.
        session_id: Owning Lens session.
        workspace_id: Active workspace (used by tool dispatch).
        owner_id: User submitting the message (used as ctx.user_id).
        user_text: The user's typed input.

    Returns:
        ``{"assistant": <text>, "tool_calls": [{"name", "args",
        "result", "status"}], "tokens_in": int, "tokens_out": int,
        "cost": float}``.

    Raises:
        LensProviderNotConfiguredError: When no enabled BYO key
            exists for the session's provider.
    """
    session = get_session(
        factory,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
    )
    api_key = decrypt_provider_key(
        factory,
        workspace_id=workspace_id,
        provider=session.llm_provider,
    )
    if api_key is None:
        raise LensProviderNotConfiguredError(
            f"No enabled {session.llm_provider!r} credential for "
            f"workspace {workspace_id}.  Add one via the admin UI."
        )

    append_message(
        factory,
        session_id=session_id,
        role="user",
        content=user_text,
    )

    provider = get_provider(session.llm_provider, api_key=api_key)
    ctx = SessionContext(
        workspace_id=workspace_id,
        user_id=owner_id,
        lens_session_id=session_id,
        factory=factory,
        settings=settings,
        uc_client=_principal_uc_client(factory, settings, owner_id),
    )

    transcript = list_session_messages(factory, session_id=session_id)
    provider_messages = to_provider_history(provider.name, transcript)

    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    observed_tool_calls: list[dict[str, Any]] = []
    iteration = 0
    final_text = ""
    while iteration < MAX_TOOL_ITERATIONS:
        iteration += 1
        completion = await provider.chat_with_tools(
            # pyright: ignore[reportAttributeAccessIssue] — system_prompt
            # is defined on ``_BaseProvider`` (which both concrete
            # providers extend) but isn't on the ``LensProvider``
            # Protocol; refactoring the Protocol to require it would
            # ripple through the test doubles, deferred.
            system=provider.system_prompt(),  # pyright: ignore[reportAttributeAccessIssue]
            messages=provider_messages,
            model=session.llm_model,
        )
        total_tokens_in += completion.tokens_in
        total_tokens_out += completion.tokens_out
        total_cost += completion.cost_estimate
        if completion.text:
            final_text = completion.text
        if not completion.tool_calls:
            # Persist the final assistant text and exit.
            append_message(
                factory,
                session_id=session_id,
                role="assistant",
                content=completion.text,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
                cost_estimate=completion.cost_estimate,
            )
            break

        # Execute each tool, persist tool-rows, and append the
        # provider-specific tool_result blocks for the next turn.
        provider_messages.append(assistant_tool_call_message(provider.name, completion))
        for call in completion.tool_calls:
            try:
                result = await execute_tool_with_audit(
                    tool_name=call.name,
                    ctx=ctx,
                    raw_args=call.args,
                )
                observed_tool_calls.append(
                    observed_tool_call_record(call.name, call.args, result, "ok")
                )
            except (LensToolError, PointlessSQLError) as exc:
                logger.info("Lens tool %s failed: %s", call.name, exc)
                result = {"error": str(exc)}
                observed_tool_calls.append(
                    observed_tool_call_record(
                        call.name, call.args, result, classify_tool_exception(exc)
                    )
                )
            provider_messages.append(tool_result_message(provider.name, call.id, result))

    # If the loop ran out of iterations without a clean assistant
    # message, persist a synthetic stop note so the transcript stays
    # complete.
    if should_persist_loop_cap(iteration, final_text, MAX_TOOL_ITERATIONS):
        final_text = loop_cap_message(MAX_TOOL_ITERATIONS)
        append_message(
            factory,
            session_id=session_id,
            role="assistant",
            content=final_text,
        )

    return completion_response(
        assistant=final_text,
        tool_calls=observed_tool_calls,
        tokens_in=total_tokens_in,
        tokens_out=total_tokens_out,
        cost=total_cost,
    )
