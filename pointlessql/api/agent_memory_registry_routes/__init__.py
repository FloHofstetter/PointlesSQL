"""Agent-memory registry — the discovery surface over agent memory.

Rolls up the existing ``agent_runs`` / ``agent_run_operations`` rows
into one entry per ``agent_id`` and lists them at ``/agent-memories``,
turning the previously unreachable per-agent memory page
(``/memory/{agent_id}``) into something you can browse to.  It adds a
view, not a store — every number is derived from tables that already
exist.

The HTML page (:mod:`._page`) and its JSON sibling (:mod:`._api`) share
the builder in :mod:`._shared`, re-exported here for direct testing.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.agent_memory_registry_routes._api import router as _api_router
from pointlessql.api.agent_memory_registry_routes._page import router as _page_router
from pointlessql.api.agent_memory_registry_routes._shared import build_registry

router = APIRouter(tags=["agent-memory-registry"])
router.include_router(_page_router)
router.include_router(_api_router)

__all__ = ["build_registry", "router"]
