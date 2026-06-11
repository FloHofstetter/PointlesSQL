"""DuckDB registration of the LLM-backed ``ai_*`` SQL functions.

Registered on the per-query connection by :func:`run_sql` whenever the
submitted SELECT references one of the names, so every governed SQL
surface (editor, notebook SQL cells, BI widgets, metric views,
pipelines) gets the same vocabulary with the same per-query budget:

* ``ai_query(prompt)`` — free-form completion.
* ``ai_classify(text, labels)`` — one label from a comma-separated set.
* ``ai_extract(text, field)`` — pull one field's value out of text.
* ``ai_translate(text, language)`` — translate into *language*.
* ``ai_mask(text)`` — deterministic PII masking (no LLM round-trip).

The runner object is supplied by the caller (see
:mod:`pointlessql.services.ai_functions`) so this module stays free of
provider and settings concerns — and tests can hand in a fake.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

AI_FUNCTION_NAMES: tuple[str, ...] = (
    "ai_query",
    "ai_classify",
    "ai_extract",
    "ai_translate",
    "ai_mask",
)

_AI_CALL_RE = re.compile(
    r"\bai_(query|classify|extract|translate|mask)\s*\(",
    re.IGNORECASE,
)


class AiRunner(Protocol):
    """The subset of the runner the UDF wrappers call."""

    def run(self, op: str, *args: str | None) -> str | None:
        """Execute one LLM-backed operation for one row."""
        ...

    def mask(self, value: str | None) -> str | None:
        """Deterministically mask *value*."""
        ...


def sql_uses_ai_functions(sql: str) -> bool:
    """Return ``True`` when *sql* textually references an ``ai_*`` call.

    A cheap pre-filter so the common no-AI query never constructs a
    runner or registers UDFs.  False positives (the pattern inside a
    string literal) only cost an idle registration — the functions
    fire per row actually evaluated, not per registration.

    Args:
        sql: The raw user SQL.

    Returns:
        Whether registration should happen for this query.
    """
    return bool(_AI_CALL_RE.search(sql))


def register_ai_functions(conn: Any, runner: AiRunner) -> None:
    """Register the ``ai_*`` scalar functions on *conn*.

    NULL handling stays on DuckDB's default (NULL in → NULL out
    without invoking the Python wrapper), and exceptions raised by the
    runner — provider failures, the per-query call budget — propagate
    as regular DuckDB errors, which :func:`run_sql` already converts
    to :class:`SQLExecutionError`.

    Args:
        conn: The per-query DuckDB connection.
        runner: Per-query executor implementing :class:`AiRunner`.
    """
    import duckdb

    def ai_query(prompt: str) -> str | None:
        return runner.run("query", prompt)

    def ai_classify(text: str, labels: str) -> str | None:
        return runner.run("classify", text, labels)

    def ai_extract(text: str, field: str) -> str | None:
        return runner.run("extract", text, field)

    def ai_translate(text: str, language: str) -> str | None:
        return runner.run("translate", text, language)

    def ai_mask(text: str) -> str | None:
        return runner.mask(text)

    specs: list[tuple[str, Any, list[str]]] = [
        ("ai_query", ai_query, ["VARCHAR"]),
        ("ai_classify", ai_classify, ["VARCHAR", "VARCHAR"]),
        ("ai_extract", ai_extract, ["VARCHAR", "VARCHAR"]),
        ("ai_translate", ai_translate, ["VARCHAR", "VARCHAR"]),
        ("ai_mask", ai_mask, ["VARCHAR"]),
    ]
    for name, fn, params in specs:
        try:
            conn.create_function(name, fn, params, "VARCHAR", side_effects=True)
        except duckdb.Error:
            # an externally-managed connection may already carry the
            # functions from a previous call — replace so the fresh
            # runner (and its fresh budget) takes over.
            conn.remove_function(name)
            conn.create_function(name, fn, params, "VARCHAR", side_effects=True)
