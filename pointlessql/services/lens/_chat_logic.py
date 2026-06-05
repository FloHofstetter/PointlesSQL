"""Pure decision and message-shaping logic for the Lens chat loop.

The chat loop is an async orchestration over the LLM provider, tool
dispatch, and the message DB.  Everything it does that is I/O-free —
rendering the transcript into provider wire shapes, echoing tool-use
blocks, wrapping tool results, JSON-encoding tool payloads, classifying
tool failures, building the observed-call records, the loop-cap policy,
and the final response envelope — lives here so it can be unit-tested
without a provider, a session factory, or a tool runtime.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pointlessql.services.lens.tools import LensToolError

if TYPE_CHECKING:
    from pointlessql.models import LensMessage


def to_provider_history(provider_name: str, transcript: list[LensMessage]) -> list[dict[str, Any]]:
    """Render the persisted transcript in the provider's wire shape.

    Tool-rows are intentionally NOT replayed (we only re-feed
    user/assistant text); the next turn's tool-calls are issued
    fresh by the LLM and the prior tool results live in
    ``lens_messages`` for the audit trail but do not pollute the
    next prompt.
    """
    out: list[dict[str, Any]] = []
    for msg in transcript:
        if msg.role == "user" and msg.content:
            if provider_name == "anthropic":
                out.append(
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": msg.content}],
                    }
                )
            else:  # openai
                out.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant" and msg.content:
            if provider_name == "anthropic":
                out.append(
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": msg.content}],
                    }
                )
            else:  # openai
                out.append({"role": "assistant", "content": msg.content})
    return out


def assistant_tool_call_message(provider_name: str, completion: Any) -> dict[str, Any]:
    """Echo the model's tool_use blocks back into the conversation."""
    if provider_name == "openai":
        return {
            "role": "assistant",
            "content": completion.text or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json_or_empty(tc.args),
                    },
                }
                for tc in completion.tool_calls
            ],
        }
    # anthropic: assistant message echoes the tool_use blocks
    blocks: list[dict[str, Any]] = []
    if completion.text:
        blocks.append({"type": "text", "text": completion.text})
    for tc in completion.tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.args,
            }
        )
    return {"role": "assistant", "content": blocks}


def tool_result_message(provider_name: str, call_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Wrap a tool-result for the provider's next-turn prompt."""
    if provider_name == "openai":
        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json_or_empty(result),
        }
    # anthropic: tool_result lives in a user-role content block
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": json_or_empty(result),
            }
        ],
    }


def json_or_empty(payload: Any) -> str:
    """Coerce *payload* to a JSON string; return ``"{}"`` on failure."""
    try:
        return json.dumps(payload, default=str)
    except TypeError, ValueError:
        return "{}"


def classify_tool_exception(exc: Exception) -> str:
    """Map a tool-dispatch failure to the observed-call status string.

    Args:
        exc: The exception raised by tool dispatch.

    Returns:
        The :class:`LensToolError`'s own ``status`` when it carries one,
        otherwise the generic ``"error"``.
    """
    if isinstance(exc, LensToolError):
        return exc.status
    return "error"


def observed_tool_call_record(
    name: str,
    args: Any,
    result: Any,
    status: str,
) -> dict[str, Any]:
    """Build one flat observed-tool-call record for the response.

    Args:
        name: The tool name.
        args: The arguments the model supplied.
        result: The tool result (or an ``{"error": ...}`` envelope).
        status: ``"ok"`` or a failure status.

    Returns:
        The flat record dict carried in the turn's ``tool_calls`` list.
    """
    return {"name": name, "args": args, "result": result, "status": status}


def should_persist_loop_cap(iteration: int, final_text: str, max_iterations: int) -> bool:
    """Decide whether to persist the synthetic loop-cap message.

    Args:
        iteration: The number of provider turns taken.
        final_text: The assistant text gathered so far.
        max_iterations: The per-turn tool-call cap.

    Returns:
        ``True`` when the loop exhausted its iterations without ever
        producing a clean assistant message.
    """
    return iteration >= max_iterations and not final_text


def loop_cap_message(max_iterations: int) -> str:
    """Render the synthetic message shown when the loop hits its cap.

    Args:
        max_iterations: The per-turn tool-call cap that was reached.

    Returns:
        A user-facing note that the iteration cap was exceeded.
    """
    return (
        "The assistant exceeded the per-turn tool-call iteration cap "
        f"({max_iterations}).  Open a new session if you need a "
        "deeper exploration."
    )


def completion_response(
    *,
    assistant: str,
    tool_calls: list[dict[str, Any]],
    tokens_in: int,
    tokens_out: int,
    cost: float,
) -> dict[str, Any]:
    """Assemble the chat-turn response envelope.

    Args:
        assistant: The final assistant text.
        tool_calls: The observed tool-call records.
        tokens_in: Total prompt tokens across all provider turns.
        tokens_out: Total completion tokens across all provider turns.
        cost: Total estimated cost across all provider turns.

    Returns:
        The dict returned by ``run_chat_turn``.
    """
    return {
        "assistant": assistant,
        "tool_calls": tool_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost": cost,
    }
