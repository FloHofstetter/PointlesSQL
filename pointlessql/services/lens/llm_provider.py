"""LLM provider adapters for the Lens browser chat-loop.

Two adapters share a thin :class:`LensProvider` Protocol so the
chat-loop is provider-agnostic:

* :class:`OpenAIProvider` wraps the official ``openai`` SDK
  (chat.completions API + tool-calling).
* :class:`AnthropicProvider` wraps the official ``anthropic`` SDK
  (messages API + tool_use blocks).

Both adapters expose one async method, :meth:`chat_with_tools`, that
takes the conversation history + tool schemas + system prompt and
returns the model's response.  Tool-call dispatch lives in the
chat-loop (:mod:`pointlessql.services.lens._chat_loop`); the
adapter is just the wire-format translator.

The adapter returns non-streaming responses; streaming + SSE
deltas are queued for a follow-up once the chat-UI proves out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pointlessql.services.lens.tools import (
    ALL_TOOLS,
    to_anthropic_schemas,
    to_openai_schemas,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    """One LLM-issued tool invocation request.

    Attributes:
        id: Provider-specific call id (echoed back as ``tool_call_id``
            on the tool-result message so multi-tool turns line up).
        name: Tool name from the registry.
        args: JSON-decoded args dict.
    """

    id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class LensCompletion:
    """One LLM round-trip result.

    Attributes:
        text: Assistant text content (may be empty when the model only
            returned tool-call requests).
        tool_calls: Tool invocation requests the chat-loop should
            dispatch before iterating again.
        tokens_in: Prompt token count from the provider.
        tokens_out: Completion token count from the provider.
        cost_estimate: Best-effort USD-ish cost.  Pricing is per
            provider + model; the chat-loop persists this on
            ``lens_messages.cost_estimate``.
        finish_reason: Provider-specific finish reason
            (``stop`` / ``tool_use`` / ``length`` / etc.).
    """

    text: str
    tool_calls: list[ToolCall]
    tokens_in: int
    tokens_out: int
    cost_estimate: float
    finish_reason: str | None


class LensProvider(Protocol):
    """Common interface every LLM adapter implements."""

    name: str

    async def chat_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 1024,
    ) -> LensCompletion:
        """Run one provider round-trip and return a normalised result."""
        ...


class _BaseProvider:
    """Shared utilities for the provider adapters."""

    @staticmethod
    def system_prompt() -> str:
        """Return the default Lens system prompt.

        The prompt anchors the analyst-role framing + read-only rule
        so the model does not hallucinate write capability.
        """
        return (
            "You are Lens, the read-only data-analyst assistant for "
            "PointlesSQL.  Use the provided tools to answer questions "
            "about catalogs, schemas, tables, and lineage.  Never "
            "claim to have written or modified data.  When a question "
            "requires SQL execution, use the 'query' tool with a "
            "single SELECT statement.  When a question is about "
            "where data came from, use the 'provenance' tool.  "
            "Always cite the table or run-id you drew the answer from."
        )


class OpenAIProvider(_BaseProvider):
    """OpenAI chat.completions adapter.

    Lazy-imports ``openai`` so the rest of PointlesSQL stays usable
    when the package isn't installed.
    """

    name: Literal["openai"] = "openai"

    def __init__(self, api_key: str) -> None:  # noqa: D107
        import openai  # local import — keeps cold-start independent

        self._client = openai.AsyncOpenAI(api_key=api_key)  # type: ignore[no-untyped-call]

    async def chat_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 1024,
    ) -> LensCompletion:
        """Run one OpenAI round-trip and return a :class:`LensCompletion`.

        Args:
            system: System prompt (rendered as a 'system' message).
            messages: Conversation history in OpenAI message-shape
                (``{"role": "user|assistant|tool", ...}``).  Tool
                results carry ``role="tool"``, ``tool_call_id``, and
                ``content``.
            model: OpenAI model identifier (e.g. ``gpt-4o-mini``).
            max_tokens: Max completion tokens.

        Returns:
            Normalised :class:`LensCompletion` carrying the assistant
            text, any tool-calls, and the token / cost estimates.
        """
        full_messages = [{"role": "system", "content": system}] + messages
        # pyright disagrees with the OpenAI SDK's ``ChatCompletionMessageParam``
        # union shape vs our internal ``list[dict[str, Any]]`` carrier;
        # rebuilding the union locally would mirror the entire OpenAI
        # types tree.  The runtime accepts our dict shape — proven by
        # the in-product /lens chat surface.
        resp = await self._client.chat.completions.create(
            model=model,
            messages=full_messages,  # pyright: ignore[reportArgumentType]
            tools=to_openai_schemas(ALL_TOOLS),  # pyright: ignore[reportArgumentType]
            max_completion_tokens=max_tokens,
        )
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for call in choice.message.tool_calls:
                args: dict[str, Any]
                try:
                    import json

                    args = json.loads(call.function.arguments or "{}")  # pyright: ignore[reportAttributeAccessIssue]
                except ValueError, TypeError:
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=str(call.id),
                        name=str(call.function.name),  # pyright: ignore[reportAttributeAccessIssue]
                        args=args,
                    )
                )
        usage = resp.usage
        tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
        return LensCompletion(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=_estimate_cost_usd(
                provider="openai",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ),
            finish_reason=str(getattr(choice, "finish_reason", "") or "") or None,
        )


class AnthropicProvider(_BaseProvider):
    """Anthropic messages adapter.

    Lazy-imports ``anthropic`` for the same reason as
    :class:`OpenAIProvider`.
    """

    name: Literal["anthropic"] = "anthropic"

    def __init__(self, api_key: str) -> None:  # noqa: D107
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def chat_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int = 1024,
    ) -> LensCompletion:
        """Run one Anthropic round-trip and return a :class:`LensCompletion`.

        Args:
            system: System prompt (passed via ``system=``).
            messages: Conversation history in Anthropic message-shape
                (``{"role": "user|assistant", "content": [...]}``).
                Tool-results live in the user-role content as a
                ``{"type": "tool_result", ...}`` block.
            model: Anthropic model identifier
                (e.g. ``claude-haiku-4-5-20251001``).
            max_tokens: Max completion tokens.

        Returns:
            Normalised :class:`LensCompletion`.
        """
        # Anthropic SDK's ``MessageParam`` union has the same
        # stub-vs-dict mismatch as the OpenAI path above; pyright's
        # complaint is structural, runtime is happy.
        resp = await self._client.messages.create(
            model=model,
            system=system,
            messages=messages,  # pyright: ignore[reportArgumentType]
            tools=to_anthropic_schemas(ALL_TOOLS),  # pyright: ignore[reportArgumentType]
            max_tokens=max_tokens,
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(str(getattr(block, "text", "")))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=str(getattr(block, "id", "")),
                        name=str(getattr(block, "name", "")),
                        args=dict(getattr(block, "input", {}) or {}),
                    )
                )
        text = "\n".join(p for p in text_parts if p).strip()
        usage = resp.usage
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        return LensCompletion(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=_estimate_cost_usd(
                provider="anthropic",
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            ),
            finish_reason=str(resp.stop_reason or "") or None,
        )


# Pricing snapshots (USD per million tokens) — best-effort; refresh
# annually.  When the model is unknown we fall back to a conservative
# upper-bound so the session-budget cap still triggers.
_OPENAI_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}
_FALLBACK_PRICING: tuple[float, float] = (5.00, 25.00)


def _estimate_cost_usd(
    *,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
) -> float:
    """Return a USD-cents-precision cost estimate for one round-trip."""
    table = (
        _OPENAI_PRICING
        if provider == "openai"
        else _ANTHROPIC_PRICING
        if provider == "anthropic"
        else {}
    )
    pricing = table.get(model, _FALLBACK_PRICING)
    in_per_million, out_per_million = pricing
    return (tokens_in / 1_000_000.0) * in_per_million + (tokens_out / 1_000_000.0) * out_per_million


def get_provider(provider_name: str, api_key: str) -> LensProvider:
    """Return a configured adapter for *provider_name*.

    Args:
        provider_name: One of :data:`pointlessql.models.LENS_PROVIDERS`.
        api_key: Cleartext API key for the provider.

    Returns:
        A :class:`LensProvider` instance.

    Raises:
        ValueError: When *provider_name* is unrecognised.
    """
    # Concrete providers have ``name: Literal["openai"]`` / ``Literal["anthropic"]``
    # but the Protocol declares ``name: str``; pyright treats the Literal
    # narrowing as covariance-failing.  Both providers DO satisfy the
    # Protocol structurally at runtime; broadening the Protocol field
    # would weaken downstream callers that branch on the literal.
    if provider_name == "openai":
        return OpenAIProvider(api_key=api_key)  # pyright: ignore[reportReturnType]
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key)  # pyright: ignore[reportReturnType]
    raise ValueError(f"Unrecognised Lens provider: {provider_name!r}")
