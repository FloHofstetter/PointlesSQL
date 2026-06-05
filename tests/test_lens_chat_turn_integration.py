"""In-process integration tests for the ``run_chat_turn`` shell.

Exercises the provider/tool loop wiring with the DB boundary, the LLM
provider, and tool dispatch all faked — verifying the orchestration the
pure ``_chat_logic`` helpers feed into: token/cost accumulation, tool
threading, the no-tool-calls exit, and the loop-cap fallback.  No live
server or real provider — runs in the default suite.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.services.lens import _chat_loop
from pointlessql.services.lens._chat_loop import MAX_TOOL_ITERATIONS, run_chat_turn
from pointlessql.services.lens.tools import LensToolError


class _FakeProvider:
    """Scripts a queue of completions; repeats the last one forever."""

    name = "openai"

    def __init__(self, completions: list[Any]) -> None:
        self._completions = completions

    def system_prompt(self) -> str:
        return "you are a test"

    async def chat_with_tools(self, *, system: str, messages: list[Any], model: str) -> Any:
        del system, messages, model
        if len(self._completions) > 1:
            return self._completions.pop(0)
        return self._completions[0]


def _completion(
    text: str,
    *,
    tool_calls: list[Any] | None = None,
    tokens_in: int = 10,
    tokens_out: int = 5,
    cost: float = 0.01,
) -> Any:
    return SimpleNamespace(
        text=text,
        tool_calls=tool_calls or [],
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimate=cost,
    )


def _tool_call(call_id: str, name: str, args: dict[str, Any]) -> Any:
    return SimpleNamespace(id=call_id, name=name, args=args)


@pytest.fixture
def appended() -> list[dict[str, Any]]:
    return []


@pytest.fixture(autouse=True)
def _patch_boundaries(monkeypatch: pytest.MonkeyPatch, appended: list[dict[str, Any]]) -> None:
    """Fake every DB / provider / UC boundary in the chat-loop module."""
    monkeypatch.setattr(
        _chat_loop,
        "get_session",
        lambda *a, **k: SimpleNamespace(llm_provider="openai", llm_model="gpt-x"),
    )
    monkeypatch.setattr(_chat_loop, "decrypt_provider_key", lambda *a, **k: "fake-key")
    monkeypatch.setattr(_chat_loop, "list_session_messages", lambda *a, **k: [])
    monkeypatch.setattr(_chat_loop, "_principal_uc_client", lambda *a, **k: None)

    def _record(*_a: Any, **kwargs: Any) -> None:
        appended.append(kwargs)

    monkeypatch.setattr(_chat_loop, "append_message", _record)


async def _run() -> dict[str, Any]:
    return await run_chat_turn(
        factory=None,  # patched boundaries ignore it
        settings=None,
        session_id=1,
        workspace_id=2,
        owner_id=3,
        user_text="hi",
    )


def _set_provider(monkeypatch: pytest.MonkeyPatch, completions: list[Any]) -> None:
    provider = _FakeProvider(completions)
    monkeypatch.setattr(_chat_loop, "get_provider", lambda *a, **k: provider)


async def test_single_turn_no_tools(
    monkeypatch: pytest.MonkeyPatch, appended: list[dict[str, Any]]
) -> None:
    _set_provider(monkeypatch, [_completion("Hello there", tokens_in=10, tokens_out=5, cost=0.02)])

    out = await _run()

    assert out["assistant"] == "Hello there"
    assert out["tool_calls"] == []
    assert out["tokens_in"] == 10
    assert out["tokens_out"] == 5
    assert out["cost"] == 0.02
    # user message + final assistant message persisted.
    roles = [m["role"] for m in appended]
    assert roles == ["user", "assistant"]


async def test_tool_then_final_threads_result_and_sums_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_provider(
        monkeypatch,
        [
            _completion("", tool_calls=[_tool_call("c1", "run_sql", {"q": "SELECT 1"})]),
            _completion("All done", tokens_in=7, tokens_out=3, cost=0.05),
        ],
    )

    async def _dispatch(*, tool_name: str, ctx: Any, raw_args: Any) -> dict[str, Any]:
        del ctx, raw_args
        return {"tool": tool_name, "rows": 3}

    monkeypatch.setattr(_chat_loop, "execute_tool_with_audit", _dispatch)

    out = await _run()

    assert out["assistant"] == "All done"
    assert out["tool_calls"] == [
        {
            "name": "run_sql",
            "args": {"q": "SELECT 1"},
            "result": {"tool": "run_sql", "rows": 3},
            "status": "ok",
        }
    ]
    # usage summed across both provider turns (10+7, 5+3, 0.01+0.05).
    assert out["tokens_in"] == 17
    assert out["tokens_out"] == 8
    assert out["cost"] == pytest.approx(0.06)


async def test_tool_error_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_provider(
        monkeypatch,
        [
            _completion("", tool_calls=[_tool_call("c1", "run_sql", {"q": "DROP TABLE t"})]),
            _completion("Recovered"),
        ],
    )

    async def _dispatch(*, tool_name: str, ctx: Any, raw_args: Any) -> dict[str, Any]:
        del ctx, raw_args
        raise LensToolError(tool_name=tool_name, message="blocked", status="non_select_blocked")

    monkeypatch.setattr(_chat_loop, "execute_tool_with_audit", _dispatch)

    out = await _run()

    (record,) = out["tool_calls"]
    assert record["status"] == "non_select_blocked"
    assert record["result"] == {"error": "blocked"}


async def test_loop_cap_persists_synthetic_message(
    monkeypatch: pytest.MonkeyPatch, appended: list[dict[str, Any]]
) -> None:
    # A provider that never stops asking for tools forces the cap.
    _set_provider(
        monkeypatch,
        [_completion("", tool_calls=[_tool_call("c", "run_sql", {})])],
    )

    async def _dispatch(*, tool_name: str, ctx: Any, raw_args: Any) -> dict[str, Any]:
        del tool_name, ctx, raw_args
        return {"ok": True}

    monkeypatch.setattr(_chat_loop, "execute_tool_with_audit", _dispatch)

    out = await _run()

    assert "iteration cap" in out["assistant"]
    assert f"({MAX_TOOL_ITERATIONS})" in out["assistant"]
    # the synthetic assistant note is persisted (user + cap message).
    assert appended[-1]["role"] == "assistant"
    assert "iteration cap" in appended[-1]["content"]
