"""Mutation-killing tests for the lens chat-loop provider formatters.

These pin the provider-specific (anthropic vs openai) wire shapes for
replayed history, assistant tool-call echoes, tool-result wrapping and
the JSON coercion helper — all pure functions over transcript rows.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.services.lens._chat_loop import (
    _assistant_tool_call_message,
    _json_or_empty,
    _to_provider_history,
    _tool_result_message,
)


def _msg(role: str, content: str | None) -> Any:
    return SimpleNamespace(role=role, content=content)


def _completion(text: str | None, tool_calls: list[Any]) -> Any:
    return SimpleNamespace(text=text, tool_calls=tool_calls)


def _tc(call_id: str, name: str, args: dict[str, Any]) -> Any:
    return SimpleNamespace(id=call_id, name=name, args=args)


# --- _to_provider_history -------------------------------------------------


def test_history_anthropic_wraps_text_blocks() -> None:
    out = _to_provider_history("anthropic", [_msg("user", "hi"), _msg("assistant", "yo")])
    assert out == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "yo"}]},
    ]


def test_history_openai_uses_plain_strings() -> None:
    out = _to_provider_history("openai", [_msg("user", "hi"), _msg("assistant", "yo")])
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]


def test_history_skips_tool_rows_and_empty_content() -> None:
    out = _to_provider_history(
        "openai",
        [_msg("tool", "result"), _msg("user", ""), _msg("assistant", "kept")],
    )
    assert out == [{"role": "assistant", "content": "kept"}]


# --- _assistant_tool_call_message -----------------------------------------


def test_assistant_tool_call_openai_shape() -> None:
    completion = _completion("thinking", [_tc("call_1", "run_sql", {"q": "SELECT 1"})])
    out = _assistant_tool_call_message("openai", completion)
    assert out == {
        "role": "assistant",
        "content": "thinking",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "run_sql", "arguments": '{"q": "SELECT 1"}'},
            }
        ],
    }


def test_assistant_tool_call_openai_empty_text_is_none() -> None:
    out = _assistant_tool_call_message("openai", _completion("", [_tc("c", "n", {})]))
    assert out["content"] is None


def test_assistant_tool_call_anthropic_blocks() -> None:
    completion = _completion("plan", [_tc("call_1", "run_sql", {"q": 1})])
    out = _assistant_tool_call_message("anthropic", completion)
    assert out == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "plan"},
            {"type": "tool_use", "id": "call_1", "name": "run_sql", "input": {"q": 1}},
        ],
    }


def test_assistant_tool_call_anthropic_omits_text_block_when_empty() -> None:
    out = _assistant_tool_call_message("anthropic", _completion(None, [_tc("c", "n", {})]))
    assert out["content"] == [{"type": "tool_use", "id": "c", "name": "n", "input": {}}]


# --- _tool_result_message -------------------------------------------------


def test_tool_result_openai_shape() -> None:
    out = _tool_result_message("openai", "call_9", {"rows": 3})
    assert out == {
        "role": "tool",
        "tool_call_id": "call_9",
        "content": '{"rows": 3}',
    }


def test_tool_result_anthropic_shape() -> None:
    out = _tool_result_message("anthropic", "call_9", {"rows": 3})
    assert out == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call_9",
                "content": '{"rows": 3}',
            }
        ],
    }


# --- _json_or_empty -------------------------------------------------------


def test_json_or_empty_serialises() -> None:
    assert _json_or_empty({"a": 1}) == '{"a": 1}'


def test_json_or_empty_uses_default_str_for_unknown_types() -> None:
    # default=str lets otherwise-unserialisable values through.
    out = _json_or_empty({"x": {1, 2}})
    assert out.startswith('{"x":')


def test_json_or_empty_returns_braces_on_failure() -> None:
    circular: dict[str, Any] = {}
    circular["self"] = circular
    assert _json_or_empty(circular) == "{}"
