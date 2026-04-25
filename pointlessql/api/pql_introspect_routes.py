"""PQL introspection endpoints — Sprint 13.11.

Sprint 13.11 closes Phase 13's read-loop: the agent already writes
into ``agent_run_operations`` / ``agent_run_tool_calls`` / Delta logs,
but had no tool to *read state* before *acting*.  Three live-walkthrough
bugs (2026-04-25) all shared that root cause.

This module hosts every ``GET /api/pql/...`` route that lets a
working-agent (Family A) check state mid-run.  Sprint 13.11.1 ships
``GET /api/pql/primitives``: introspection over the :class:`PQL`
public methods so an agent that gets a ``TypeError`` from
``pql.autoload(source=...)`` can ask for the real signature.
Subsequent sub-sprints layer ``target-state`` (13.11.2),
``recent-failures`` (13.11.2), and ``lineage`` (13.11.3) on top.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import APIRouter

from pointlessql.pql.pql import PQL

router = APIRouter(tags=["pql-introspect"])

# Public primitive surface of :class:`PQL` exposed to agents.  Order
# mirrors the medallion authoring flow: read → query → write/update →
# bootstrap.  Helper methods (``list_*``, the private ``_unreachable_msg``)
# are deliberately omitted — agents reach catalog metadata through
# ``pql_list_tables`` / ``pql_get_table`` instead.
_PRIMITIVES: tuple[str, ...] = (
    "table",
    "sql",
    "write_table",
    "merge",
    "autoload",
)


def _build_primitive_specs() -> dict[str, dict[str, Any]]:
    """Snapshot signatures and docstrings for the public PQL primitives.

    Computed once at import time and frozen — the PQL surface is part
    of the package, not a runtime-mutable contract, so a process-level
    cache is the right granularity.  The route handler returns the
    same dict on every call without re-introspecting.

    Returns:
        ``{name: {"name", "signature", "doc"}}`` for each primitive in
        :data:`_PRIMITIVES`.
    """
    specs: dict[str, dict[str, Any]] = {}
    for name in _PRIMITIVES:
        method = getattr(PQL, name)
        signature = str(inspect.signature(method))
        doc = inspect.getdoc(method) or ""
        specs[name] = {
            "name": name,
            "signature": f"{name}{signature}",
            "doc": doc,
        }
    return specs


_PRIMITIVE_SPECS: dict[str, dict[str, Any]] = _build_primitive_specs()


@router.get("/api/pql/primitives")
async def api_pql_primitives() -> dict[str, Any]:
    """Return the introspected signature + docstring for every PQL primitive.

    Designed for the Sprint-13.11.1 ``pql_describe_primitive`` Hermes
    tool.  The plugin filters the response client-side so the LLM
    only sees one primitive at a time, but the server returns the
    full set in one round-trip — five entries fit comfortably in a
    single response and avoid a per-name HTTP hop when an agent
    wants to compare ``write_table`` vs ``merge`` vs ``autoload``
    before picking one.

    Returns:
        ``{"primitives": {"autoload": {...}, ...}}`` — the inner dicts
        carry ``name``, ``signature`` (e.g.
        ``"autoload(self, source_path: str, target: str, *, ...)"``),
        and ``doc`` (the Google-style docstring verbatim).
    """
    return {"primitives": _PRIMITIVE_SPECS}


__all__ = ["router"]
