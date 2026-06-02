"""Unit tests for the editor-chat agent factory's pre-import logic.

``check_llm_configured`` is pure. ``build_agent`` guards on it, then sets the
surface-specific session env vars before lazily importing the hermes agent —
that env-routing is covered by isolating ``os.environ`` (so the direct
assignments don't leak) and faking the ``run_agent`` module so no real agent
is constructed.
"""

from __future__ import annotations

import os
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services.editor_chat._agent_factory import (
    _PROVIDER_ENV_KEYS,
    build_agent,
    check_llm_configured,
)


def _settings() -> Any:
    return SimpleNamespace(
        editor_chat=SimpleNamespace(default_model="m", provider=None, base_url=None)
    )


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Give the factory a throwaway ``os.environ`` and a fake hermes module."""
    env: dict[str, str] = {}
    monkeypatch.setattr(os, "environ", env)
    fake = types.ModuleType("run_agent")
    fake.AIAgent = lambda **kw: SimpleNamespace(kwargs=kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "run_agent", fake)
    return env


# --- check_llm_configured -------------------------------------------------


def test_check_llm_configured_false_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    assert check_llm_configured() is False


def test_check_llm_configured_true_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert check_llm_configured() is True


# --- build_agent ----------------------------------------------------------


def test_build_agent_without_llm_raises(isolated_env: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="No LLM provider"):
        build_agent(
            settings=_settings(),
            agent_run_id="run-1",
            editor_session_id="sess-1",
            on_token=lambda _t: None,
        )


def test_build_agent_sql_surface_sets_chat_session(isolated_env: dict[str, str]) -> None:
    isolated_env["ANTHROPIC_API_KEY"] = "sk-x"
    isolated_env["POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID"] = "stale"
    build_agent(
        settings=_settings(),
        agent_run_id="run-1",
        editor_session_id="sess-sql",
        on_token=lambda _t: None,
        surface="sql",
    )
    assert isolated_env["POINTLESSQL_CHAT_SESSION_ID"] == "sess-sql"
    assert isolated_env["POINTLESSQL_AGENT_RUN_ID"] == "run-1"
    # The notebook surface's var is cleared so its propose tools don't register.
    assert "POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID" not in isolated_env


def test_build_agent_notebook_surface_sets_notebook_vars(isolated_env: dict[str, str]) -> None:
    isolated_env["ANTHROPIC_API_KEY"] = "sk-x"
    isolated_env["POINTLESSQL_CHAT_SESSION_ID"] = "stale"
    build_agent(
        settings=_settings(),
        agent_run_id="run-2",
        editor_session_id="sess-nb",
        on_token=lambda _t: None,
        surface="notebook",
        notebook_id="nb-9",
    )
    assert isolated_env["POINTLESSQL_NOTEBOOK_CHAT_SESSION_ID"] == "sess-nb"
    assert isolated_env["POINTLESSQL_NOTEBOOK_ID"] == "nb-9"
    assert "POINTLESSQL_CHAT_SESSION_ID" not in isolated_env
