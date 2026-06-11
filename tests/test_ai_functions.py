"""AI SQL functions: runner budget/cache, registration, run_sql wiring."""

from __future__ import annotations

from pathlib import Path

import deltalake
import duckdb
import pandas as pd
import pytest

from pointlessql.config import Settings
from pointlessql.exceptions import SQLExecutionError
from pointlessql.pql import PQL
from pointlessql.pql._ai_functions import (
    register_ai_functions,
    sql_uses_ai_functions,
)
from pointlessql.services import ai_functions as ai_service
from pointlessql.services.ai_functions import AiFunctionRunner

# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def test_detection_matches_known_calls_case_insensitively() -> None:
    assert sql_uses_ai_functions("SELECT AI_CLASSIFY(name, 'a,b') FROM t")
    assert sql_uses_ai_functions("select ai_query('hi')")
    assert not sql_uses_ai_functions("SELECT aim_query(x) FROM t")
    assert not sql_uses_ai_functions("SELECT name FROM ai_query_logs")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


def _runner(calls: list[tuple[str, str]], **settings_kwargs: object) -> AiFunctionRunner:
    settings = Settings()
    for key, value in settings_kwargs.items():
        object.__setattr__(settings.ai_functions, key, value)

    def completer(system: str, user: str) -> str:
        calls.append((system, user))
        return f"answer-{len(calls)}"

    return AiFunctionRunner(settings, completer=completer)


def test_runner_caches_repeated_argument_tuples() -> None:
    calls: list[tuple[str, str]] = []
    runner = _runner(calls)
    first = runner.run("classify", "apple", "fruit,animal")
    second = runner.run("classify", "apple", "fruit,animal")
    assert first == second == "answer-1"
    assert len(calls) == 1
    assert "Labels: fruit,animal" in calls[0][1]
    assert "Text: apple" in calls[0][1]


def test_runner_enforces_per_query_call_budget() -> None:
    calls: list[tuple[str, str]] = []
    runner = _runner(calls, max_calls_per_query=2)
    runner.run("query", "a")
    runner.run("query", "b")
    with pytest.raises(SQLExecutionError, match="budget"):
        runner.run("query", "c")
    # cached values stay servable after the budget is exhausted.
    assert runner.run("query", "a") == "answer-1"


def test_runner_null_first_argument_short_circuits() -> None:
    calls: list[tuple[str, str]] = []
    runner = _runner(calls)
    assert runner.run("query", None) is None
    assert calls == []


def test_runner_truncates_long_outputs() -> None:
    settings = Settings()
    object.__setattr__(settings.ai_functions, "max_output_chars", 5)
    runner = AiFunctionRunner(settings, completer=lambda s, u: "x" * 100)
    assert runner.run("query", "p") == "xxxxx"


def test_mask_is_deterministic_and_needs_no_provider() -> None:
    runner = AiFunctionRunner(Settings(), completer=None)
    masked = runner.mask("alice@example.com")
    assert masked is not None
    assert "alice@example.com" not in masked
    assert runner.mask(None) is None


def test_unconfigured_runner_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    runner = AiFunctionRunner(Settings(), completer=None)
    with pytest.raises(SQLExecutionError, match="configured LLM provider"):
        runner.run("query", "hello")


# ---------------------------------------------------------------------------
# DuckDB registration
# ---------------------------------------------------------------------------


class _FakeRunner:
    def run(self, op: str, *args: str | None) -> str | None:
        if args and args[0] is None:
            return None
        return f"{op}:{'/'.join(a or '' for a in args)}"

    def mask(self, value: str | None) -> str | None:
        return None if value is None else "***"


def test_registered_functions_evaluate_per_row() -> None:
    conn = duckdb.connect()
    register_ai_functions(conn, _FakeRunner())
    rows = conn.execute(
        "SELECT ai_classify(v, 'a,b'), ai_mask(v) "
        "FROM (VALUES ('x'), ('y'), (NULL)) t(v) ORDER BY 1 NULLS LAST"
    ).fetchall()
    assert rows[0] == ("classify:x/a,b", "***")
    assert rows[1] == ("classify:y/a,b", "***")
    assert rows[2] == (None, None)


def test_double_registration_replaces_cleanly() -> None:
    conn = duckdb.connect()
    register_ai_functions(conn, _FakeRunner())
    register_ai_functions(conn, _FakeRunner())
    out = conn.execute("SELECT ai_query('p')").fetchone()
    assert out == ("query:p",)


# ---------------------------------------------------------------------------
# run_sql wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def fruit_delta(tmp_path: Path) -> str:
    loc = str(tmp_path / "fruit")
    df = pd.DataFrame({"name": ["apple", "apple", "dog"]})
    deltalake.write_deltalake(loc, df)
    return loc


def test_run_sql_registers_and_executes_ai_functions(
    fruit_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_service, "build_runner", lambda settings=None: _FakeRunner())
    result = PQL.sql(
        "SELECT name, ai_classify(name, 'fruit,animal') AS label "
        "FROM main.demo.fruit ORDER BY name",
        approved_tables={"main.demo.fruit": fruit_delta},
    )
    assert result.rows[0] == ["apple", "classify:apple/fruit,animal"]
    assert result.rows[2] == ["dog", "classify:dog/fruit,animal"]


def test_run_sql_budget_error_surfaces_as_sql_error(
    fruit_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings()
    object.__setattr__(settings.ai_functions, "max_calls_per_query", 1)

    def completer(system: str, user: str) -> str:
        return "ok"

    monkeypatch.setattr(
        ai_service,
        "build_runner",
        lambda s=None: AiFunctionRunner(settings, completer=completer),
    )
    with pytest.raises(SQLExecutionError, match="budget"):
        PQL.sql(
            "SELECT ai_query(name) FROM main.demo.fruit",
            approved_tables={"main.demo.fruit": fruit_delta},
        )


def test_run_sql_skips_registration_when_disabled(
    fruit_delta: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pointlessql import config as config_module

    settings = Settings()
    object.__setattr__(settings.ai_functions, "enabled", False)
    monkeypatch.setattr(config_module, "get_settings", lambda: settings)
    with pytest.raises(SQLExecutionError, match="ai_query"):
        PQL.sql(
            "SELECT ai_query(name) FROM main.demo.fruit",
            approved_tables={"main.demo.fruit": fruit_delta},
        )
