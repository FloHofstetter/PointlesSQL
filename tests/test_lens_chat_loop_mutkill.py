"""Mutation-killing tests for the lens chat-loop pure logic.

These pin the provider-specific (anthropic vs openai) wire shapes for
replayed history, assistant tool-call echoes, tool-result wrapping and
the JSON coercion helper, plus the tool-failure classifier, the
observed-call record, the loop-cap policy/message, and the response
envelope — every I/O-free piece in
``pointlessql.services.lens._chat_logic``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pointlessql.exceptions import PointlessSQLError
from pointlessql.services.lens._chat_logic import (
    assistant_tool_call_message,
    classify_tool_exception,
    completion_response,
    json_or_empty,
    loop_cap_message,
    observed_tool_call_record,
    should_persist_loop_cap,
    to_provider_history,
    tool_result_message,
)
from pointlessql.services.lens.tools import LensToolError


def _msg(role: str, content: str | None) -> Any:
    return SimpleNamespace(role=role, content=content)


def _completion(text: str | None, tool_calls: list[Any]) -> Any:
    return SimpleNamespace(text=text, tool_calls=tool_calls)


def _tc(call_id: str, name: str, args: dict[str, Any]) -> Any:
    return SimpleNamespace(id=call_id, name=name, args=args)


# --- to_provider_history -------------------------------------------------


def test_history_anthropic_wraps_text_blocks() -> None:
    out = to_provider_history("anthropic", [_msg("user", "hi"), _msg("assistant", "yo")])
    assert out == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "yo"}]},
    ]


def test_history_openai_uses_plain_strings() -> None:
    out = to_provider_history("openai", [_msg("user", "hi"), _msg("assistant", "yo")])
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "yo"},
    ]


def test_history_skips_tool_rows_and_empty_content() -> None:
    out = to_provider_history(
        "openai",
        [_msg("tool", "result"), _msg("user", ""), _msg("assistant", "kept")],
    )
    assert out == [{"role": "assistant", "content": "kept"}]


# --- assistant_tool_call_message -----------------------------------------


def test_assistant_tool_call_openai_shape() -> None:
    completion = _completion("thinking", [_tc("call_1", "run_sql", {"q": "SELECT 1"})])
    out = assistant_tool_call_message("openai", completion)
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
    out = assistant_tool_call_message("openai", _completion("", [_tc("c", "n", {})]))
    assert out["content"] is None


def test_assistant_tool_call_anthropic_blocks() -> None:
    completion = _completion("plan", [_tc("call_1", "run_sql", {"q": 1})])
    out = assistant_tool_call_message("anthropic", completion)
    assert out == {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "plan"},
            {"type": "tool_use", "id": "call_1", "name": "run_sql", "input": {"q": 1}},
        ],
    }


def test_assistant_tool_call_anthropic_omits_text_block_when_empty() -> None:
    out = assistant_tool_call_message("anthropic", _completion(None, [_tc("c", "n", {})]))
    assert out["content"] == [{"type": "tool_use", "id": "c", "name": "n", "input": {}}]


# --- tool_result_message -------------------------------------------------


def test_tool_result_openai_shape() -> None:
    out = tool_result_message("openai", "call_9", {"rows": 3})
    assert out == {
        "role": "tool",
        "tool_call_id": "call_9",
        "content": '{"rows": 3}',
    }


def test_tool_result_anthropic_shape() -> None:
    out = tool_result_message("anthropic", "call_9", {"rows": 3})
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


# --- json_or_empty -------------------------------------------------------


def test_json_or_empty_serialises() -> None:
    assert json_or_empty({"a": 1}) == '{"a": 1}'


def test_json_or_empty_uses_default_str_for_unknown_types() -> None:
    # default=str lets otherwise-unserialisable values through.
    out = json_or_empty({"x": {1, 2}})
    assert out.startswith('{"x":')


def test_json_or_empty_returns_braces_on_failure() -> None:
    circular: dict[str, Any] = {}
    circular["self"] = circular
    assert json_or_empty(circular) == "{}"


# --- classify_tool_exception ----------------------------------------------


def test_classify_tool_exception_uses_lens_status() -> None:
    exc = LensToolError(tool_name="run_sql", message="nope", status="denied")
    assert classify_tool_exception(exc) == "denied"


def test_classify_tool_exception_generic_is_error() -> None:
    assert classify_tool_exception(PointlessSQLError("boom")) == "error"


# --- observed_tool_call_record --------------------------------------------


def test_observed_tool_call_record_shape() -> None:
    rec = observed_tool_call_record("run_sql", {"q": "SELECT 1"}, {"rows": 2}, "ok")
    assert rec == {
        "name": "run_sql",
        "args": {"q": "SELECT 1"},
        "result": {"rows": 2},
        "status": "ok",
    }


# --- should_persist_loop_cap ----------------------------------------------


def test_should_persist_loop_cap_true_when_capped_and_no_text() -> None:
    assert should_persist_loop_cap(8, "", 8) is True


def test_should_persist_loop_cap_false_when_text_present() -> None:
    assert should_persist_loop_cap(8, "answer", 8) is False


def test_should_persist_loop_cap_false_below_cap() -> None:
    assert should_persist_loop_cap(3, "", 8) is False


# --- loop_cap_message -----------------------------------------------------


def test_loop_cap_message_names_the_cap() -> None:
    msg = loop_cap_message(8)
    assert "iteration cap" in msg
    assert "(8)" in msg


# --- completion_response --------------------------------------------------


def test_completion_response_envelope() -> None:
    assert completion_response(
        assistant="done",
        tool_calls=[{"name": "t"}],
        tokens_in=10,
        tokens_out=20,
        cost=1.5,
    ) == {
        "assistant": "done",
        "tool_calls": [{"name": "t"}],
        "tokens_in": 10,
        "tokens_out": 20,
        "cost": 1.5,
    }
